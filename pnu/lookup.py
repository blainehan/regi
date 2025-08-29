import pandas as pd
import re

class PnuLookup:
    def __init__(self, csv_path: str):
        self.df = pd.read_csv(csv_path, dtype=str)
        self.df.fillna("", inplace=True)
        self.df["full_name"] = (
            self.df["시도명"].str.strip() + " " +
            self.df["시군구명"].str.strip() + " " +
            self.df["읍면동명"].str.strip()
        )

    def lookup(self, query: str) -> dict:
        q = re.sub(r"\s+", " ", query.strip())

        candidates = self.df[self.df["full_name"].str.contains(q)]
        if len(candidates) == 1:
            row = candidates.iloc[0]
            return {"ok": True, "pnu10": row["adm_cd10"], "matched": row["full_name"]}
        elif len(candidates) > 1:
            return {
                "ok": False,
                "error": "동명이인 지역이 여러 개 있습니다. 시군구까지 입력해주세요.",
                "candidates": candidates["full_name"].tolist()
            }
        else:
            return {"ok": False, "error": "지역명을 찾을 수 없습니다."}