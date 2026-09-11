
from FlagEmbedding import BGEM3FlagModel
model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, device="cpu")
output = model.encode("我爱你", return_sparse=True)
sparse = output['lexical_weights']
tokenizer = model.tokenizer
print("输入: 我爱你")
print(f"词表大小: {tokenizer.vocab_size}, 非零: {len(sparse)}")
for tid, weight in sorted(sparse.items(), key=lambda x: -x[1])[:20]:
    token = tokenizer.decode([tid])
    print(f"  ID {tid:>6}  '{token}'  {weight:.4f}")
