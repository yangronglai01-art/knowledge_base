# knowledge_base/query_process/nodes/node_item_name_confirm.py

import json
from typing import Tuple, Dict, List

from langchain_core.messages import SystemMessage, HumanMessage

from knowledge_base.config.config import lm_config, milvus_config
from knowledge_base.query_process.base import NodeBase
from knowledge_base.query_process.prompt import ITEM_NAME_EXTRACT_SYSTEM_PROMPT, ITEM_NAME_EXTRACT_TEMPLATE
from knowledge_base.query_process.state import QueryGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.embedding_utils import generate_embeddings
from knowledge_base.utils.llm_utils import get_llm_client
from knowledge_base.utils.milvus_utils import hybrid_search, create_hybrid_search_request
from knowledge_base.utils.mongo_history_utils import save_chat_message, format_json, get_recent_messages, \
    update_message_item_names


class NodeItemNameConfirm(NodeBase):
    """
    节点功能：确认用户问题中的核心商品名称。
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_item_name_confirm"

    def process(self, state: QueryGraphState):
        """
        节点逻辑
        :param state: 工作流状态对象
        :return: 更新后的状态对象
        """

        # 1. 参数校验
        session_id, original_query = self._step1_validate_param(state)

        # 2. 获取聊天历史记录
        history = get_recent_messages(session_id)

        # 3. 保存用户当前问题
        message_id = save_chat_message(session_id, "user", original_query)

        # 4. 提取问题中的商品名称，并改写用户问题（调用LLM）
        extract_result = self._step4_extract_info(original_query, history)
        item_names = extract_result.get("item_names")
        rewritten_query = extract_result.get("rewritten_query")

        # 5. & 6. 如果有提取到商品名，进行搜索和对齐
        align_result = {}
        if len(item_names) > 0:
            # 向量转换和混合查询
            query_results = self._step5_vectorize_and_query(item_names)
            # 评分对齐
            align_result = self._step6_align_item_names(query_results)
        else:
            logger.warning("未提取到商品名，跳过向量检索")

        # 7. 检查确认状态
        dict_result = self._step7_check_confirmation(align_result, history)

        # 8. 写入最终历史
        self._step8_write_history(dict_result, session_id, original_query, rewritten_query, message_id)

        # 9. 返回结果
        return {
            "history": get_recent_messages(session_id),
            "rewritten_query": rewritten_query,
            "item_names": dict_result.get("item_names"),
            "answer": dict_result.get("answer"),
        }

    def _step1_validate_param(self, state: QueryGraphState) -> Tuple[str, str]:

        session_id = state.get("session_id")
        if not session_id:
            raise ValueError("核心参数session_id缺失")

        original_query = state.get("original_query")
        if not original_query:
            raise ValueError("核心参数original_query缺失")

        return session_id, original_query

    def _step4_extract_info(self, original_query, history) -> Dict:


        try:

            # 1. 组织提示词
            history_text = ""
            for msg in reversed(history):
                history_text += f"{msg.get('role')}: {msg.get('text')}\n"


            user_prompt = ITEM_NAME_EXTRACT_TEMPLATE.format(
                history_text=history_text,
                original_query=original_query
            )

            # 2. 创建消息对象
            messages = [
                SystemMessage(content=ITEM_NAME_EXTRACT_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt)
            ]

            # 3. 调用模型
            # 如果想让模型返回结构化的结果:例如json，要做两件事
            # 1） 设置 response_format = {"type": "json_object"}
            # 2）在提示词中明确要返回json结果，并且定义返回的具体格式
            llm_client= get_llm_client(model=lm_config.item_model, json_mode=True)
            response = llm_client.invoke(messages)

            # 4. 获取响应
            content = response.content

            # 5. 数据清洗：处理LLM可能返回的代码块格式（如```json ... ```），去除包裹符
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "")

            # 6. json字符串转成字典
            result = json.loads(content)


            # 7. 获取商品名称，并改写用户问题
            if "item_names" not in result:
                result["item_names"] = []

            if "rewritten_query" not in result:
                result["rewritten_query"] = original_query

            # 8. 给item_names 去除空格
            result["item_names"] = [
                name.replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "")
                for name in result["item_names"]
            ]

            return result

        except Exception as e:
            logger.exception(f"商品信息提取失败：{e}")
            return {"item_names":[], "rewritten_query": original_query}

    def _step5_vectorize_and_query(self, item_names) -> List[Dict]:
        """
        将item_names中的商品名逐个向量化，然后执行混合搜索，获取评分
        :return: 格式：
            [
                {
                    "extracted_name": "hak180烫金机"
                    "matches": [                          # 该商品名的TopN匹配结果，无则空列表
                        {
                            "item_name": "ExampleCorp X100工业设备",  # Milvus中存储的标准化商品名
                            "score": 0.80                  # 混合搜索的相似度评分（0-1，越高越相似）
                        },
                        {
                            "item_name": "ExampleCorp X90工业设备",  # Milvus中存储的标准化商品名
                            "score": 0.80                  # 混合搜索的相似度评分（0-1，越高越相似）
                        },
                    ]
                },
                ...
            ]
        """

        embeddings = generate_embeddings(item_names)
        dense_vectors = embeddings["dense"]
        sparse_vectors = embeddings["sparse"]

        results = []

        for i, item_name in enumerate(item_names):


            reqs = create_hybrid_search_request(
                dense_vector=dense_vectors[i], sparse_vector=sparse_vectors[i]
            )

            collection_name = milvus_config.item_name_collection
            search_result = hybrid_search(
                collection_name=collection_name,
                reqs=reqs,
                ranker_weights=(0.8, 0.2),
                norm_score=True, # 归一化
                output_fields=["item_name"]
            )

            hits = search_result[0]
            matches = [{"item_name": hit.get("entity").get("item_name"), "score": hit.get("distance")} for hit in hits]


            results.append({
                "extracted_name": item_name,
                "matches": matches
            })

        return results

    def _step6_align_item_names(self, query_results: List[Dict]) -> Dict:

        # 返回最终对齐结果：确认列表和候选列表均做去重处理（list(set())）
        # 根据Milvus搜索评分，逐个对齐step4提取的item_names，生成「确认商品名」和「候选商品名」
        #     对齐规则（优先级a>b>c）：
        #             a  如果评分高于0.85 → 直接确认该商品名
        #             b  如果无0.85分以上结果 → 取分数≥0.6的最高前3个作为候选
        #             c  如果无0.6分及以上结果 → 不返回任何商品名（确认+候选均为空）


        # 1. 初始化确认列表
        confirmed_item_names : List[str] = []

        # 2. 初始化候选列表
        options : List[str] = []

        # 3. 迭代上一步的结果数据
        for res in query_results:

            # 3.1 获取匹配到的商品名列表
            matches = res.get("matches")

            # 3.2 健壮性判断
            if not matches:
                continue

            # 筛选评分高于0.85分的匹配结果
            high = [m for m in matches if m.get("score") > 0.85]
            # 筛选评分大于等于0.6，小于等于0.85的数据
            mid = [m for m in matches if m.get("score") >= 0.6]

            # a  如果评分高于0.85 → 直接确认该商品名
            if len(high) > 0:
                confirmed_item_names += [m.get("item_name") for m in high]
                continue

            # b  如果无0.85分以上结果 → 取分数≥0.6的最高前3个作为候选
            if len(mid) > 0:
                options += [m.get("item_name") for m in mid[:3]]
                continue

            #  c  如果无0.6分及以上结果 → 不返回任何商品名（确认+候选均为空）
            logger.info(f"无0.85分以上结果，无0.6分及以上结果")

        # 返回结果
        return {
            "confirmed_item_names": list(set(confirmed_item_names)),  # 去重，避免重复确认
            "options": list(set(options))  # 去重，避免重复候选
        }

    def _step7_check_confirmation(self, align_result, history):
        """
        1.  **分支A（有确认商品）**：更新 State 中的 `item_names`，并批量回填历史消息中缺失的商品名关联。
        2.  **分支B（有候选选项）**：生成澄清反问句（如“您是指...吗？”），写入 State 的 `answer` 字段，清空 `item_names`。
        3.  **分支C（无结果）**：生成拒识回复（如“未找到相关产品...”），写入 State 的 `answer` 字段。
        """

        # 获取确认的商品名称
        confirmed_item_names = align_result.get("confirmed_item_names")
        # 获取候选选项（需要澄清）
        options = align_result.get("options")

        # Fallback: if prev assistant offered options and user confirmed, auto-resolve
        if not confirmed_item_names and not options and history:
            last_assistant = None
            last_user = None
            for msg in reversed(history):
                if msg.get("role") == "assistant" and not last_assistant:
                    last_assistant = msg.get("text", "")
                if msg.get("role") == "user" and not last_user:
                    last_user = msg.get("text", "")
            if last_assistant and last_assistant.startswith("您是想咨询以下哪个产品：") and last_assistant.endswith("，请明确"):
                option_from_history = last_assistant.replace("您是想咨询以下哪个产品：", "").replace("，请明确", "")
                # Check if user confirmed (repeated the option or said yes)
                confirm_words = ["嗯嗯", "对", "是", "就是", "这个", "yes", "确认", "对的", "是的"]
                if any(w in (last_user or "") for w in confirm_words) or option_from_history in (last_user or ""):
                    confirmed_item_names = [option_from_history]
                    logger.info(f"Fallback confirmed: {confirmed_item_names}")

        # 分支A（有确认商品）
        if confirmed_item_names:

            # 收集历史消息中未关联商品名的消息id，以便进行批量更新
            ids_to_update = [str(msg.get("_id")) for msg in history if not msg.get("item_names")]


            # 如果存在待更新的消息id，则批量更新商品名
            if ids_to_update:
                update_message_item_names(ids_to_update, confirmed_item_names)

            return {
                "item_names": confirmed_item_names,
                "answer": "" # 无answer
            }

        # 分支B（有候选商品）
        if options:
            # 只有1个候选时自动确认，不反问
            if len(options) == 1:
                confirmed_item_names = options
                ids_to_update = [str(msg.get("_id")) for msg in history if not msg.get("item_names")]
                if ids_to_update:
                    update_message_item_names(ids_to_update, confirmed_item_names)
                return {
                    "item_names": confirmed_item_names,
                    "answer": ""
                }
            option_str= "、".join(options)
            return {
                "item_names": [],
                "answer": f"您是想咨询以下哪个产品：{option_str}，请明确" # 有answer
            }

        # 分支C（无结果）
        return {
            "item_names": [],
            "answer": "抱歉，未找到相关产品，请提供准确的商品型号和商品名称。" # 有answer
        }

    def _step8_write_history(self, dict_result, session_id, original_query, rewritten_query, message_id):

        if dict_result.get("answer"):

            # 插入新记录
            save_chat_message(
                session_id = session_id,
                role = "assistant",
                text = dict_result.get("answer"),
                rewritten_query = "",
                item_names = []
            )

        # 强制更新本次用户原始问题的关联信息（核心：补充改写查询、商品名）
        save_chat_message(
            session_id=session_id,  # 会话ID，关联所属会话
            role="user",  # 消息角色：用户
            text=original_query,  # 消息内容：用户原始查询
            rewritten_query=rewritten_query,  # 补充step3改写后的完整问题
            item_names=dict_result.get("item_names", []),  # 补充关联的商品名列表
            message_id=message_id  # 消息ID，指定更新已存在的用户消息（而非新增）
        )


if __name__ == "__main__":

    # 模拟会话历史
    session_id = "test_001"
    save_chat_message(session_id, "user", "咨询下烫金机。")
    save_chat_message(session_id, "assistant", "您好。请问是哪个型号")
    save_chat_message(session_id, "user", "hak180")
    save_chat_message(session_id, "assistant", "具体有什么问题呢？")

    # 初始化图状态
    init_state = {
        "session_id": "test_001",
        "original_query": "ExampleCorp X100工业设备怎么使用？"
    }

    # 创建节点对象
    node_item_name_confirm = NodeItemNameConfirm()
    # 执行节点的单元测试
    result = node_item_name_confirm(init_state)
    # 将返回的图状态进行json序列化
    logger.info(format_json(result))
