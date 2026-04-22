import pickle

with open("known_faces_encodings.pkl", "rb") as f:
    data = pickle.load(f)

print(type(data))
print(data)