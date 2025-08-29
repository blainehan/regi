from fastapi import FastAPI, Query
from lookup import PnuLookup
import os

app = FastAPI()

csv_path = os.path.join(os.path.dirname(__file__), "../pnu10.csv")
pnu_lookup = PnuLookup(csv_path)

@app.get("/")
def root():
    return {"message": "✅ /convert?query=서울 서초구 양재동 으로 호출하세요."}

@app.get("/convert")
def convert(query: str = Query(...)):
    return pnu_lookup.lookup(query)