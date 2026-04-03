# tools_nutrition_local.py
from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Literal
from collections import defaultdict
import pandas as pd
import re, json

# ------------------------------ Config ---------------------------------

TSV_PATH = Path("opennutrition_foods.tsv")
JSON_COLS = [
    "alternate_names","source","serving","nutrition_100g",
    "labels","ingredients","ingredient_analysis"
]

# health score knobs (0..100 total)
# tune weights transparently as needed
SCORE_WEIGHTS = {
    "sodium_per_5mg": 20,       # up to -20 points (sodium/5)
    "added_sugar_per_g": 2,     # per 1 g added sugar, up to -20
    "sat_fat_per_g": 2,         # per 1 g sat fat, up to -20
    "cal_per_25": 10,           # calories/25, up to -10
    "fiber_per_g": 2,           # +2 per g, up to +10
    "protein_per_g": 1,         # +1 per g, up to +10
}

GOALS = Literal["general_health","low_sodium","low_sugar","high_protein"]

# ---------------------------- Utilities --------------------------------

def _safe_json(x: Any):
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return json.loads(s)
    except Exception:
        # lenient: single quotes → double quotes
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            # if it's already a scalar or list-like string, keep as-is
            return s

def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _norm_ingredients(ing: Any) -> Optional[List[str]]:
    """Return a cleaned list of ingredient phrases (or None)."""
    if ing is None:
        return None
    if isinstance(ing, list):
        out = [re.sub(r"\s+", " ", str(i)).strip(" ,;") for i in ing if str(i).strip()]
        return out or None
    if isinstance(ing, str):
        parts = re.split(r"[;,]\s*", ing.strip())
        out = [re.sub(r"\s+", " ", p).strip(" ,;") for p in parts if p]
        return out or None
    return None

def _norm_token(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9+\- ]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t

def _tokenize_ingredients(ing: Any) -> List[str]:
    lst = _norm_ingredients(ing) or []
    toks: List[str] = []
    for item in lst:
        for tok in re.split(r"[ /,\-()]+", item.lower()):
            tok = tok.strip()
            if len(tok) >= 2:
                toks.append(tok)
    return toks

# --------------------------- Data Loading -------------------------------

_DF: Optional[pd.DataFrame] = None
_ING_INDEX = defaultdict(set)   # token -> set(row_idx)

def _build_ing_index(df: pd.DataFrame):
    _ING_INDEX.clear()
    if "ingredients" not in df.columns:
        return
    for i, row in df.iterrows():
        toks = _tokenize_ingredients(row.get("ingredients"))
        for tok in toks:
            _ING_INDEX[tok].add(i)

def _make_search_text(row: pd.Series) -> str:
    names = [row.get("name","")]
    alts = row.get("alternate_names")
    if isinstance(alts, list):
        names += alts
    elif isinstance(alts, str):
        names.append(alts)
    return " | ".join([n for n in names if n]).lower()

def _load_tsv(tsv: Path) -> pd.DataFrame:
    df = pd.read_csv(tsv, sep="\t", dtype=str, keep_default_na=False)
    for c in JSON_COLS:
        if c in df.columns:
            df[c] = df[c].apply(_safe_json)
    df["_search_text"] = df.apply(_make_search_text, axis=1)
    # clean EAN if present
    if "ean_13" in df.columns:
        df["_ean"] = df["ean_13"].astype(str).str.replace(r"\D", "", regex=True)
    else:
        df["_ean"] = ""
    _build_ing_index(df)
    return df

def _ensure_df():
    global _DF
    if _DF is None:
        if not TSV_PATH.exists():
            raise FileNotFoundError(f"TSV not found at {TSV_PATH.resolve()}")
        _DF = _load_tsv(TSV_PATH)

# ------------------------- Nutrition & Scoring --------------------------

_NUT_KEYS = {
    "calories": 0.0,
    "protein": 0.0,
    "total_fat": 0.0,
    "saturated_fats": 0.0,
    "carbohydrates": 0.0,
    "total_sugars": 0.0,
    "added_sugars": 0.0,
    "sodium": 0.0,
    "dietary_fiber": 0.0,
    "cholesterol": 0.0,
}

def _project_nutrients(n100g: dict | None) -> dict:
    out = dict(_NUT_KEYS)
    if isinstance(n100g, dict):
        for k in out.keys():
            out[k] = _to_float(n100g.get(k), 0.0)
    return out

def _grams_per_serving(serving: dict | None) -> float:
    """Return grams per serving if metric is in grams; else default 100g."""
    if not isinstance(serving, dict):
        return 100.0
    metric = serving.get("metric") if isinstance(serving.get("metric"), dict) else {}
    if metric.get("unit") == "g":
        return _to_float(metric.get("quantity"), 100.0)
    # If unit is ml, you can optionally assume density≈1 and treat as grams
    if metric.get("unit") == "ml":
        return _to_float(metric.get("quantity"), 100.0)
    return 100.0

def _health_score_100g(n: dict) -> int:
    # Penalties
    score = 100.0
    score -= _clamp(n["sodium"] / 5.0, 0, SCORE_WEIGHTS["sodium_per_5mg"])
    sugar = n.get("added_sugars", n.get("total_sugars", 0.0))
    score -= _clamp(sugar * SCORE_WEIGHTS["added_sugar_per_g"], 0, 20)
    score -= _clamp(n["saturated_fats"] * SCORE_WEIGHTS["sat_fat_per_g"], 0, 20)
    score -= _clamp(n["calories"] / 25.0, 0, SCORE_WEIGHTS["cal_per_25"])
    # Credits
    score += _clamp(n["dietary_fiber"] * SCORE_WEIGHTS["fiber_per_g"], 0, 10)
    score += _clamp(n["protein"] * SCORE_WEIGHTS["protein_per_g"], 0, 10)
    return int(round(_clamp(score, 0, 100)))

_ALLERGEN_TOKENS = {
    "egg","milk","peanut","hazelnut","almond","walnut","cashew","pistachio","pecan",
    "tree nut","wheat","gluten","barley","rye","soy","fish","shellfish","sesame"
}

def _infer_warnings(n: dict, ingredients_text: str | None, ingredient_analysis: dict | None) -> List[str]:
    warns: list[str] = []
    if n["sodium"] > 400: warns.append("high sodium (per 100g)")
    sugar = n.get("added_sugars", n.get("total_sugars", 0.0))
    if sugar > 5: warns.append("added sugars (per 100g)")
    if n["saturated_fats"] > 5: warns.append("high saturated fat (per 100g)")
    if n.get("cholesterol", 0.0) > 200: warns.append("high cholesterol (per 100g)")

    if isinstance(ingredients_text, str) and ingredients_text:
        low = ingredients_text.lower()
        for token in _ALLERGEN_TOKENS:
            if token in low:
                warns.append(f"contains {token}")
        if "palm oil" in low: warns.append("contains palm oil")
        if "hfcs" in low or "high fructose corn syrup" in low:
            warns.append("contains high-fructose corn syrup")

    if isinstance(ingredient_analysis, dict) and ingredient_analysis:
        warns.append("ingredient analysis available")

    seen = set(); uniq = []
    for w in warns:
        if w not in seen:
            uniq.append(w); seen.add(w)
    return uniq

# ------------------------ Payload & Lookups -----------------------------

def _payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """Standard enriched payload returned to the agent."""
    n_raw = row.get("nutrition_100g")
    n = _project_nutrients(n_raw if isinstance(n_raw, dict) else None)
    ing_raw = row.get("ingredients")
    ing_list = _norm_ingredients(ing_raw)
    grams = _grams_per_serving(row.get("serving") if isinstance(row.get("serving"), dict) else None)
    factor = grams / 100.0
    n_serv = {k: round(v * factor, 3) for k, v in n.items()}

    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "type": row.get("type"),
        "ean_13": row.get("ean_13"),
        "labels": row.get("labels"),
        "ingredients_raw": ing_raw,
        "ingredients_list": ing_list,
        "serving": row.get("serving"),
        "nutrition_100g": n,
        "nutrition_per_serving": n_serv,
        "score_100g": _health_score_100g(n),
        "warnings": _infer_warnings(
            n=n,
            ingredients_text=(ing_raw if isinstance(ing_raw, str) else None),
            ingredient_analysis=(row.get("ingredient_analysis") if isinstance(row.get("ingredient_analysis"), dict) else None),
        ),
        "source": row.get("source"),
    }

def lookup_by_barcode_local(ean_13: str) -> Optional[Dict[str, Any]]:
    _ensure_df()
    code = re.sub(r"\D", "", str(ean_13))
    hits = _DF[_DF["_ean"] == code]  # type: ignore[index]
    return None if hits.empty else _payload(hits.iloc[0].to_dict())

def lookup_by_name_local(name: str, top_k: int = 5) -> List[Dict[str, Any]]:
    _ensure_df()
    q = name.lower().strip()
    def score(txt: str) -> float:
        if not txt: return 0.0
        if q in txt: return 1.0 + len(q) / max(1, len(txt))
        tq = set(re.findall(r"\w+", q)); tt = set(re.findall(r"\w+", txt))
        return 0.0 if not tq or not tt else len(tq & tt) / len(tq | tt)
    s = _DF["_search_text"].apply(score)                 # type: ignore[index]
    hits = _DF.loc[s > 0].copy()                         # type: ignore[index]
    if hits.empty: return []
    hits["_score"] = s[s > 0]
    hits.sort_values("_score", ascending=False, inplace=True)
    return [_payload(r.to_dict()) for _, r in hits.head(top_k).iterrows()]

# --------------------- Ingredients-Only Flow ---------------------------

_WARN_PATTERNS = [
    (r"\b(salt|sodium|msg|monosodium\s+glutamate)\b", "high-sodium ingredient(s)"),
    (r"\b(sugar|dextrose|glucose|fructose|syrup|hfcs|high\s*fructose)\b", "added sugars"),
    (r"\b(palm\s+oil|hydrogenated|partially\s+hydrogenated|shortening|trans\s*fats?)\b", "unhealthy oils/trans fats"),
    (r"\b(artificial\s+color|color\s*added|red\s*40|yellow\s*5|blue\s*1|caramel\s+color)\b", "artificial colors"),
    (r"\b(artificial\s+flavor|flavour)\b", "artificial flavors"),
    (r"\b(preservative|bht|bha|sodium\s+benzoate|nitrite|nitrate)\b", "preservatives"),
    (r"\b(soy|wheat|gluten|milk|egg|peanut|almond|walnut|cashew|pistachio|hazelnut|sesame|fish|shellfish)\b", "common allergen"),
]

def assess_ingredients_text(ingredients_text: str) -> Dict[str, Any]:
    text = (ingredients_text or "").lower()
    warnings: List[str] = []
    for pat, label in _WARN_PATTERNS:
        if re.search(pat, text):
            warnings.append(label)
    # dedup preserve order
    seen=set(); warnings=[w for w in warnings if not (w in seen or seen.add(w))]
    return {"warnings": warnings}

def lookup_by_ingredients_local(ingredients_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Rank foods by ingredient token overlap + fallback text similarity."""
    _ensure_df()
    if not ingredients_text:
        return []

    toks = _tokenize_ingredients(ingredients_text)
    if not toks:
        return []

    # Gather candidates via inverted index
    cand_idxs = set()
    for t in toks:
        for idx in _ING_INDEX.get(t, []):
            cand_idxs.add(idx)

    # Fallback: also consider text similarity to names
    q = ingredients_text.lower()
    def score_text(txt: str) -> float:
        if not txt: return 0.0
        if q in txt: return 1.0 + len(q)/max(1,len(txt))
        tq = set(re.findall(r"\w+", q)); tt = set(re.findall(r"\w+", txt))
        return 0.0 if not tq or not tt else len(tq & tt) / len(tq | tt)

    text_scores = _DF["_search_text"].apply(score_text)  # type: ignore[index]
    text_hits = set(_DF.index[text_scores > 0].tolist()) # type: ignore[index]
    cand_idxs |= text_hits

    if not cand_idxs:
        return []

    # Rank: Jaccard of ingredient tokens (when available) + text score
    def jaccard(row: pd.Series) -> float:
        row_toks = set(_tokenize_ingredients(row.get("ingredients")))
        if not row_toks:
            return 0.0
        inter = len(row_toks & set(toks))
        union = len(row_toks | set(toks))
        return inter / union if union else 0.0

    rows = _DF.loc[list(cand_idxs)].copy()  # type: ignore[index]
    rows["_jacc"] = rows.apply(lambda r: jaccard(r), axis=1)
    rows["_txt"]  = text_scores.loc[rows.index]         # type: ignore[index]
    rows["_score"]= rows["_jacc"] * 0.8 + rows["_txt"] * 0.2
    rows.sort_values("_score", ascending=False, inplace=True)

    return [_payload(r.to_dict()) for _, r in rows.head(top_k).iterrows()]

# ------------------------- Alternatives --------------------------------

def _passes_goal(n: dict, goal: GOALS) -> bool:
    if goal == "low_sodium":
        return n["sodium"] < 300
    if goal == "low_sugar":
        sugar = n.get("added_sugars", n.get("total_sugars", 0.0))
        return sugar <= 5
    if goal == "high_protein":
        return n["protein"] >= 10
    return True

def _alternatives_like(base_payload: Dict[str, Any],
                       top_k: int = 5,
                       goal: GOALS = "general_health") -> List[Dict[str, Any]]:
    """Find items with same 'type' when possible, meaningfully higher score, filtered by goal."""
    _ensure_df()
    base_score = int(base_payload.get("score_100g", 0))
    base_type = base_payload.get("type")
    df = _DF
    if isinstance(base_type, str) and base_type:
        df = df[df["type"] == base_type]  # type: ignore[index]

    def proj(r: pd.Series):
        return _payload(r.to_dict())

    cands = [proj(r) for _, r in df.iterrows()]
    better = [p for p in cands
              if p["id"] != base_payload["id"]
              and p["score_100g"] >= base_score + 10
              and _passes_goal(p["nutrition_100g"], goal)]
    # prefer snacks if label/type suggests snack; else just by score delta
    def key(p):
        delta = p["score_100g"] - base_score
        is_snack = 1 if (p.get("type") == "snack" or ("labels" in p and isinstance(p["labels"], list) and "snack" in p["labels"])) else 0
        return (is_snack, delta, p["score_100g"])

    better.sort(key=key, reverse=True)
    return better[:top_k]

# ---------------------- High-level entry points -------------------------

def lookup_by_name_assessed(name: str, top_k: int = 5,
                            goal: GOALS = "general_health") -> List[Dict[str, Any]]:
    """Lookup by name; each result includes warnings, score, and alternatives."""
    matches = lookup_by_name_local(name, top_k=top_k)
    out: List[Dict[str, Any]] = []
    for m in matches:
        m["alternatives"] = _alternatives_like(m, top_k=top_k, goal=goal)
        out.append(m)
    return out

def assess_from_ingredients(ingredients_text: str, top_k: int = 5,
                            goal: GOALS = "general_health") -> Dict[str, Any]:
    """Ingredients-only path: warnings + TSV candidates + goal-aware alternatives."""
    assess = assess_ingredients_text(ingredients_text)
    cands  = lookup_by_ingredients_local(ingredients_text, top_k=top_k)

    alternatives: List[Dict[str, Any]] = []
    if cands:
        best = cands[0]
        alternatives = _alternatives_like(best, top_k=top_k, goal=goal)

    return {
        "input_ingredients": ingredients_text,
        "warnings": assess["warnings"],
        "matches": cands,              # enriched payloads (score, nutrients, etc.)
        "alternatives": alternatives,  # derived from best match (if any)
    }

# ---------------------------- Public API --------------------------------

def load_tsv(tsv: Union[str, Path]) -> pd.DataFrame:
    return _load_tsv(Path(tsv))

def reload_tsv(tsv: Union[str, Path]) -> int:
    """Refresh the module-global DF and indices; returns row count."""
    global _DF, TSV_PATH
    TSV_PATH = Path(tsv)
    _DF = _load_tsv(TSV_PATH)
    return len(_DF)

__all__ = [
    "load_tsv",
    "reload_tsv",
    "lookup_by_barcode_local",
    "lookup_by_name_local",
    "lookup_by_name_assessed",
    "lookup_by_ingredients_local",
    "assess_from_ingredients",
]
