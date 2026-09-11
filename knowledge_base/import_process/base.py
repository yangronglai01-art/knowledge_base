import time
from abc import ABC, abstractmethod

from knowledge_base.import_process.state import ImportGraphState
from knowledge_base.tool.logger import logger
from knowledge_base.utils.task_utils import add_running_task, add_done_task, add_node_duration


class NodeBase(ABC):

    name: str = "node_base"

    def __init__(self):
        """
        强制子类设置name
        """
        if self.name == "node_base":
            raise ValueError(f"{self.__class__.__name__} 必须设置 name 属性")

    def __call__(self, state: ImportGraphState):

        try:

            task_id = state.get("task_id", "")

            # 1. 记录节点的运行状态:开始
            add_running_task(task_id, self.name)

            # 2. 记录开始时间
            start_time = time.time()

            # 3. 执行节点
            result = self.process(state)

            # 4. 记录结束时间
            end_time = time.time()

            # 5. 记录节点的运行状态:结束
            add_done_task(task_id, self.name)

            # 6. 记录节点运行时间
            add_node_duration(task_id, self.name, end_time - start_time)

            return result

        except Exception as e:
            logger.error(f"{self.name} 执行失败：{e}")
            raise

    @abstractmethod
    def process(self: ImportGraphState):
        """
        节点的核心处理逻辑
        :return:
        """
        pass
