from pymilvus import AnnSearchRequest

dense_params = {"nprobe": 10}
limit = 5
expr = ""
query_text = "white headphones, quiet and comfortable"
dense_vector = [0.3580376395471989, -0.6023495712049978, 0.5142999509918703, ...]

# text semantic search (dense)
# search_param_1 = {
#     "data": [query_dense_vector],
#     "anns_field": "text_dense",
#     "param": {"nprobe": 10},
#     "limit": 2
# }
# request_1 = AnnSearchRequest(**search_param_1)

# text semantic search (dense)
request_1 = AnnSearchRequest(
    data= [dense_vector],
    anns_field= "dense_vector",
    param= dense_params,
    limit= limit,
    expr=expr
)