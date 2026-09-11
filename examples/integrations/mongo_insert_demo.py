from pymongo import MongoClient



myclient = MongoClient("mongodb://localhost:27017/")
mydb = myclient["knowledge_base_demo"]
mycol = mydb["users"]

user1 = {"name": "Annie", "age": 100, "sex": "female"}

result = mycol.insert_one(user1)
print(result)
