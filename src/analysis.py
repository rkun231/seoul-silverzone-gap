"""
서울 교통약자(노인·어린이) 보행안전 데이터 분석
- 데이터: TAAS(도로교통공단) 보행사고·사고다발지역·보호구역, 행정안전부 주민등록인구, 서울 자치구 경계
- 실행: python src/analysis.py  (프로젝트 루트에서)
- 출력: outputs/figures/*.png, outputs/tables/*.csv, outputs/summary.json
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib import font_manager
from shapely.geometry import Point
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EXT = ROOT / "data" / "ext"
FIG = ROOT / "outputs" / "figures"
TAB = ROOT / "outputs" / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)

# ---------- 스타일 ----------
for f in font_manager.findSystemFonts():
    if "NotoSansCJK-Regular" in f or "NotoSansCJK-Bold" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": "Noto Sans CJK JP",
    "axes.unicode_minus": False,
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#9a9893",
    "axes.labelcolor": "#52514e",
    "xtick.color": "#52514e",
    "ytick.color": "#52514e",
    "axes.titleweight": "bold",
    "axes.titlesize": 10.5,
    "axes.titlelocation": "left",
    "figure.dpi": 200,
})
C_OLD = "#2a78d6"     # 노인(카테고리 1)
C_CHILD = "#eb6834"   # 어린이(카테고리 2)
C_ACC = "#1baf7a"
GRAY = "#b8b6b0"
INK = "#0b0b0b"
INK2 = "#52514e"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
CRS = "EPSG:5179"     # TAAS 좌표계(UTM-K, GRS80)


def save(fig, name):
    fig.savefig(FIG / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


S = {}  # 보고서용 요약 수치

# ---------- 1. 데이터 적재 ----------
old = pd.read_csv(RAW / "taas_seoul_elderly_ped_accidents_2021_2025.csv")
chd = pd.read_csv(RAW / "taas_seoul_child_ped_accidents_2021_2025.csv")
for d in (old, chd):
    d["gu"] = d["legaldong_name"].str.replace("서울특별시 ", "", regex=False).str.strip()
    d["cas"] = d[["dprs_cnt", "sep_cnt", "slp_cnt", "inj_aplcnt_cnt"]].sum(axis=1)
    d["ksi"] = d["dprs_cnt"] + d["sep_cnt"]           # 사망+중상
    d["hour"] = d["occrrnc_time_dc"].str.replace("시", "", regex=False).astype(int)
    d["crossing"] = d["acdnt_dc"].str.contains("횡단중")

zones = pd.read_csv(RAW / "taas_seoul_protection_zones_points.csv")
zones = zones[zones["useYn"] == "Y"].copy()
zones["year"] = pd.to_numeric(zones["assignDt"].str[:4], errors="coerce")
zones["gu"] = zones["addr"].str.split().str[1]
zg = gpd.GeoDataFrame(zones, geometry=gpd.points_from_xy(zones.x, zones.y), crs=CRS)
silver = zg[zg.fcltyTy == 2]
school = zg[zg.fcltyTy == 1]

hz = pd.read_csv(RAW / "taas_seoul_ped_hotspot_zones.csv")
ha = pd.read_csv(RAW / "taas_seoul_ped_hotspot_accidents.csv")

pop = pd.read_csv(RAW / "mois_pop_seoul_202609.csv")
def agesum(lo, hi):
    sel = [c for c in pop.columns if (m := re.fullmatch(r"(\d+)세(남자|여자)", c)) and lo <= int(m.group(1)) <= hi]
    return pop[sel].sum(axis=1)
pop["p65"] = agesum(65, 200)
pop["p0_12"] = agesum(0, 12)
gpop = pop.groupby("시군구명")[["계", "p65", "p0_12"]].sum().rename(columns={"계": "total"})
S["pop_total"] = int(gpop.total.sum())
S["pop65"] = int(gpop.p65.sum())
S["pop0_12"] = int(gpop.p0_12.sum())
S["share65"] = round(gpop.p65.sum() / gpop.total.sum() * 100, 1)

# ---------- 2. 연도별 추이 (노인 vs 어린이) ----------
def yearly(d):
    g = d.groupby("acdnt_year").agg(acc=("acdnt_no", "count"), dead=("dprs_cnt", "sum"),
                                     ksi=("ksi", "sum"), cas=("cas", "sum"))
    return g
yo, yc = yearly(old), yearly(chd)
yt = yo.add_prefix("old_").join(yc.add_prefix("child_"))
yt.to_csv(TAB / "t1_yearly_old_vs_child.csv", encoding="utf-8-sig")
S["old_acc_5y"] = int(yo.acc.sum()); S["child_acc_5y"] = int(yc.acc.sum())
S["old_dead_5y"] = int(yo.dead.sum()); S["child_dead_5y"] = int(yc.dead.sum())
S["old_acc_2021"] = int(yo.acc[2021]); S["old_acc_2025"] = int(yo.acc[2025])
S["old_acc_growth"] = round((yo.acc[2025] / yo.acc[2021] - 1) * 100, 1)
S["child_acc_2021"] = int(yc.acc[2021]); S["child_acc_2025"] = int(yc.acc[2025])
S["old_fatal_rate"] = round(yo.dead.sum() / yo.cas.sum() * 100, 2)
S["child_fatal_rate"] = round(yc.dead.sum() / yc.cas.sum() * 100, 2)
S["old_ksi_share"] = round(yo.ksi.sum() / yo.cas.sum() * 100, 1)
S["child_ksi_share"] = round(yc.ksi.sum() / yc.cas.sum() * 100, 1)

fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw={"wspace": 0.35})
x = np.arange(len(yo.index)); w = 0.38
ax = axes[0]
b1 = ax.bar(x - w/2 - 0.01, yo.acc, w, color=C_OLD, label="노인(65+) 보행자")
b2 = ax.bar(x + w/2 + 0.01, yc.acc, w, color=C_CHILD, label="어린이(12세 이하) 보행자")
for xi, v in zip(x, yo.acc):
    ax.text(xi - w/2, v + 25, f"{v:,}", ha="center", va="bottom", fontsize=6.5, color=INK2)
ax.set_xticks(x, [str(i) for i in yo.index]); ax.set_ylabel("사고 건수")
ax.set_title("① 서울 보행 교통사고 건수 (2021~2025)")
ax.legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(0, 1.0))
ax.set_ylim(0, yo.acc.max() * 1.25)
ax.grid(axis="y", color="#e8e6e1", lw=0.6); ax.set_axisbelow(True)
ax = axes[1]
cats = ["노인(65+)", "어린이(≤12)"]
vals = [yo.dead.sum(), yc.dead.sum()]
bars = ax.bar(cats, vals, color=[C_OLD, C_CHILD], width=0.5)
for bb, v, r in zip(bars, vals, [S["old_fatal_rate"], S["child_fatal_rate"]]):
    ax.text(bb.get_x() + bb.get_width()/2, v + 6, f"{v}명\n(치사율 {r}%)", ha="center", va="bottom", fontsize=7.5, color=INK)
ax.set_ylim(0, max(vals) * 1.35); ax.set_ylabel("사망자 수 (5년 합계)")
ax.set_title("② 5년간 보행 사망자")
ax.grid(axis="y", color="#e8e6e1", lw=0.6); ax.set_axisbelow(True)
save(fig, "fig1_trend.png")

# ---------- 3. 보호구역 수급 불일치 ----------
S["n_silver"] = int(len(silver)); S["n_school"] = int(len(school))
S["silver_per_10k65"] = round(len(silver) / gpop.p65.sum() * 1e4, 2)
S["school_per_10k012"] = round(len(school) / gpop.p0_12.sum() * 1e4, 2)
S["silver_per_100acc"] = round(len(silver) / yo.acc.sum() * 100, 1)
S["school_per_100acc"] = round(len(school) / yc.acc.sum() * 100, 1)
S["ratio_per_acc"] = round(S["school_per_100acc"] / S["silver_per_100acc"], 1)
yrs = list(range(2016, 2027))
sy = silver.groupby("year").size().reindex(yrs, fill_value=0)
S["silver_new_2016_2021"] = int(sy.loc[2016:2021].sum())
S["silver_new_2022_2026"] = int(sy.loc[2022:2026].sum())
S["silver_by_year"] = {int(k): int(v) for k, v in sy.items()}
S["silver_types"] = silver.fcltyDetailTyNm.value_counts().to_dict()

fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.5), gridspec_kw={"wspace": 0.45, "width_ratios": [1, 1.3]})
ax = axes[0]
cats = ["어린이보호구역", "노인보호구역"]
vals = [S["school_per_100acc"], S["silver_per_100acc"]]
bars = ax.bar(cats, vals, color=[C_CHILD, C_OLD], width=0.5)
for bb, v, n in zip(bars, vals, [len(school), len(silver)]):
    ax.text(bb.get_x() + bb.get_width()/2, v + 2, f"{v}곳\n(총 {n:,}곳)", ha="center", va="bottom", fontsize=7.5, color=INK)
ax.set_ylim(0, 115); ax.set_ylabel("보행사고 100건당 보호구역 수")
ax.set_title(f"③ 사고 대비 보호구역 공급 ({S['ratio_per_acc']}배 차이)")
ax.grid(axis="y", color="#e8e6e1", lw=0.6); ax.set_axisbelow(True)
ax = axes[1]
ax.bar([f"'{str(y)[2:]}" for y in yrs], sy.values, color=C_OLD, width=0.6)
for i, v in enumerate(sy.values):
    ax.text(i, v + 0.6, str(v), ha="center", fontsize=6.5, color=INK2)
ax.set_title("④ 서울 노인보호구역 신규 지정 (지정연도별)")
ax.set_ylabel("개소"); ax.tick_params(axis="x", labelsize=7)
ax.set_ylim(0, sy.max() * 1.25)
ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
ax.grid(axis="y", color="#e8e6e1", lw=0.6); ax.set_axisbelow(True)
save(fig, "fig2_supply.png")

# ---------- 4. 자치구별 위험도 vs 공급 ----------
gu_old = old.groupby("gu").agg(acc=("acdnt_no", "count"), cas=("cas", "sum"), ksi=("ksi", "sum"), dead=("dprs_cnt", "sum"))
gu = gpop.join(gu_old, how="left").fillna(0)
gu["silver"] = silver.groupby("gu").size().reindex(gu.index, fill_value=0)
gu["cas_per_10k65_yr"] = gu.cas / 5 / gu.p65 * 1e4          # 노인 1만명당 연평균 보행 사상자
gu["ksi_per_10k65_yr"] = gu.ksi / 5 / gu.p65 * 1e4
gu["silver_per_10k65"] = gu.silver / gu.p65 * 1e4
gu["share65"] = gu.p65 / gu.total * 100
# 보호 공백 지수: 위험(사망·중상률) 표준화 - 공급(노인 1만명당 실버존) 표준화
z = lambda s: (s - s.mean()) / s.std()
gu["gap_index"] = z(gu.ksi_per_10k65_yr) - z(gu.silver_per_10k65)
gu = gu.sort_values("gap_index", ascending=False)
gu.round(3).to_csv(TAB / "t2_gu_risk_supply.csv", encoding="utf-8-sig")
S["gu_top5_gap"] = gu.head(5).index.tolist()
S["gu_table_top"] = gu.head(6)[["p65", "ksi", "ksi_per_10k65_yr", "silver", "silver_per_10k65", "gap_index"]].round(2).reset_index().to_dict("records")
r = np.corrcoef(gu.ksi_per_10k65_yr, gu.silver_per_10k65)[0, 1]
S["corr_risk_supply"] = round(float(r), 2)

seoul = gpd.read_file(EXT / "seoul_municipalities_geo_simple.json").to_crs(CRS)
seoul = seoul.merge(gu.reset_index().rename(columns={"index": "gu", "시군구명": "gu"}), left_on="name", right_on="gu", how="left")

fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.3), gridspec_kw={"wspace": 0.28, "width_ratios": [1.05, 1]})
ax = axes[0]
from matplotlib.colors import ListedColormap, BoundaryNorm
q = np.quantile(seoul.ksi_per_10k65_yr, [0, .2, .4, .6, .8, 1])
cmap = ListedColormap(SEQ[1:6]); norm = BoundaryNorm(q, cmap.N)
seoul.plot(ax=ax, column="ksi_per_10k65_yr", cmap=cmap, norm=norm, edgecolor="white", linewidth=0.8)
for _, rw in seoul.iterrows():
    c = rw.geometry.representative_point()
    ax.text(c.x, c.y, rw["name"], ha="center", va="center", fontsize=5.2,
            color="white" if rw.ksi_per_10k65_yr >= q[3] else INK)
ax.set_axis_off(); ax.set_title("⑤ 노인 1만 명당 연평균 보행 사망·중상자")
from matplotlib.patches import Patch
handles = [Patch(color=SEQ[i+1], label=f"{q[i]:.1f}~{q[i+1]:.1f}") for i in range(5)]
ax.legend(handles=handles, frameon=False, fontsize=6, loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=5, title="명/노인 1만 명·년", title_fontsize=6, handlelength=1.2, columnspacing=0.8)
ax = axes[1]
ax.scatter(gu.silver_per_10k65, gu.ksi_per_10k65_yr, s=gu.p65 / 900, color=C_OLD, alpha=0.75, edgecolor="white", linewidth=1.2)
mx, my = gu.silver_per_10k65.median(), gu.ksi_per_10k65_yr.median()
ax.axvline(mx, color=GRAY, lw=0.8, ls="--"); ax.axhline(my, color=GRAY, lw=0.8, ls="--")
lab = set(gu.head(6).index) | set(gu.sort_values("silver_per_10k65", ascending=False).head(3).index)
for name, rw in gu.iterrows():
    if name in lab:
        ax.annotate(name, (rw.silver_per_10k65, rw.ksi_per_10k65_yr), xytext=(4, 3), textcoords="offset points", fontsize=6.5, color=INK)
ax.text(0.02, 0.98, "위험 높고\n보호 부족", transform=ax.transAxes, va="top", fontsize=7, color="#e34948", fontweight="bold")
ax.set_xlabel("노인 1만 명당 노인보호구역(개소)"); ax.set_ylabel("연평균 사망·중상자(노인 1만 명당)")
ax.set_title("⑥ 자치구별 위험 대비 보호 공급")
ax.grid(color="#efede8", lw=0.6); ax.set_axisbelow(True)
save(fig, "fig3_gu.png")

# ---------- 5. 사고 발생 특성 (시간·요일·유형) ----------
dorder = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
hm = old.pivot_table(index="dfk_dc", columns="hour", values="acdnt_no", aggfunc="count").reindex(dorder).fillna(0)
S["old_daytime_share"] = round((old.tmzon_div_1_dc == "주간").mean() * 100, 1)
S["old_crossing_share"] = round(old.crossing.mean() * 100, 1)
S["child_crossing_share"] = round(chd.crossing.mean() * 100, 1)
peak = old.groupby("hour").size()
S["old_peak_hours"] = peak.sort_values(ascending=False).head(3).index.tolist()
S["old_9to18_share"] = round(old.hour.between(9, 17).mean() * 100, 1)
# 횡단 중 사고의 치명도
cr = old.groupby("crossing").apply(lambda d: d.ksi.sum() / d.cas.sum() * 100)
S["ksi_rate_crossing"] = round(float(cr[True]), 1); S["ksi_rate_noncross"] = round(float(cr[False]), 1)
night = old.groupby("tmzon_div_1_dc").apply(lambda d: d.dprs_cnt.sum() / d.cas.sum() * 100)
S["fatal_rate_night"] = round(float(night["야간"]), 2); S["fatal_rate_day"] = round(float(night["주간"]), 2)
veh = old.wrngdo_vhcle_asort_dc.value_counts(normalize=True).mul(100).round(1)
S["veh_share"] = veh.head(7).to_dict()
road = old.road_stle_dc.str.split(" - ").str[0].value_counts(normalize=True).mul(100).round(1)
S["road_share"] = road.to_dict()
viol = old.lrg_violt_1_dc.value_counts(normalize=True).mul(100).round(1)
S["viol_share"] = viol.head(4).to_dict()

fig, axes = plt.subplots(1, 2, figsize=(7.4, 2.5), gridspec_kw={"wspace": 0.75, "width_ratios": [1.6, 1]})
ax = axes[0]
im = ax.imshow(hm.values, aspect="auto", cmap=ListedColormap(SEQ), interpolation="nearest")
ax.set_yticks(range(7), [d[0] for d in dorder]); ax.set_xticks(range(0, 24, 3), [f"{h}시" for h in range(0, 24, 3)])
ax.set_title("⑦ 노인 보행사고 요일×시간대 (건, 2021~2025)")
cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02); cb.ax.tick_params(labelsize=6); cb.outline.set_visible(False)
for s in ax.spines.values(): s.set_visible(False)
ax = axes[1]
labels = ["횡단 중", "기타", "차도 통행", "보도 통행", "길가장자리"]
key = ["횡단중", "차대사람 - 기타", "차도통행중", "보도통행중", "길가장자리구역통행중"]
vals = [old.acdnt_dc.str.contains(k).sum() / len(old) * 100 for k in key]
ksir = [old[old.acdnt_dc.str.contains(k)].ksi.sum() / old[old.acdnt_dc.str.contains(k)].cas.sum() * 100 for k in key]
yy = np.arange(len(labels))
ax.barh(yy, vals, color=C_OLD, height=0.55)
for i, (v, k) in enumerate(zip(vals, ksir)):
    ax.text(v + 1, i, f"{v:.0f}%  (중상 이상 {k:.0f}%)", va="center", fontsize=6.5, color=INK2)
ax.set_yticks(yy, labels); ax.invert_yaxis(); ax.set_xlim(0, 75)
ax.set_xlabel("사고 비중(%)"); ax.set_title("⑧ 사고 유형별 비중")
save(fig, "fig4_pattern.png")

# ---------- 6. 다발지 공간분석: 노인보호구역 커버리지 ----------
h25 = hz[(hz.kind == "보행노인") & (hz.selYear == "25년")].copy()
hg = gpd.GeoDataFrame(h25, geometry=gpd.points_from_xy(h25.xCrdnt, h25.yCrdnt), crs=CRS)
def nearest_dist(src, tgt):
    arr = np.vstack([tgt.geometry.x, tgt.geometry.y]).T
    out = []
    for p in src.geometry:
        d = np.sqrt(((arr - [p.x, p.y]) ** 2).sum(axis=1))
        out.append(d.min())
    return np.array(out)
hg["d_silver"] = nearest_dist(hg, silver)
hg["d_school"] = nearest_dist(hg, school)
S["n_hot25"] = int(len(hg))
S["hot25_cas"] = int(hg.caltCnt.sum()); S["hot25_dead"] = int(hg.dprsCnt.sum())
S["hot25_within300_silver"] = int((hg.d_silver <= 300).sum())
S["hot25_within300_silver_pct"] = round((hg.d_silver <= 300).mean() * 100, 1)
S["hot25_within300_school_pct"] = round((hg.d_school <= 300).mean() * 100, 1)
S["hot25_median_d_silver"] = int(np.median(hg.d_silver))
S["hot25_over1km_pct"] = round((hg.d_silver > 1000).mean() * 100, 1)

# 반복성: 23·24·25년 선정 다발지 중 반경 100m 내 중복
def persist(base, other):
    o = other[["xCrdnt", "yCrdnt"]].values
    return np.array([np.sqrt(((o - [x, y]) ** 2).sum(axis=1)).min() <= 100 for x, y in base[["xCrdnt", "yCrdnt"]].values])
h24 = hz[(hz.kind == "보행노인") & (hz.selYear == "24년")]
h23 = hz[(hz.kind == "보행노인") & (hz.selYear == "23년")]
hg["in24"] = persist(h25, h24); hg["in23"] = persist(h25, h23)
hg["repeat"] = hg.in24.astype(int) + hg.in23.astype(int)
S["hot25_repeat_any"] = int((hg.repeat >= 1).sum()); S["hot25_repeat_all3"] = int((hg.repeat == 2).sum())

# 다발지별 사고 특성 → K-means 유형화
a25 = ha[(ha.kind == "보행노인") & (ha.selYear == "25년")].copy()
a25["hour"] = a25.occrrnc_time_dc.str.replace("시", "", regex=False).astype(int)
a25g = gpd.GeoDataFrame(a25, geometry=gpd.points_from_xy(a25.xCrdnt, a25.yCrdnt), crs=CRS)
# 각 사고를 가장 가까운 다발지에 귀속
hxy = hg[["xCrdnt", "yCrdnt"]].values
a25g["zoneCode"] = [hg.zoneCode.values[np.argmin(((hxy - [x, y]) ** 2).sum(axis=1))] for x, y in a25[["xCrdnt", "yCrdnt"]].values]
feat = a25g.groupby("zoneCode").agg(
    n=("acdnt_no", "count"),
    night=("tmzon_div_1_dc", lambda s: (s == "야간").mean()),
    crossing=("acdnt_dc", lambda s: s.str.contains("횡단중").mean()),
    intersection=("road_stle_dc", lambda s: s.str.startswith("교차로").mean()),
    two_wheel=("wrngdo_vhcle_asort_dc", lambda s: s.isin(["이륜", "자전거", "개인형이동수단(PM)", "원동기"]).mean()),
    heavy=("wrngdo_vhcle_asort_dc", lambda s: s.isin(["화물", "승합", "건설기계", "특수"]).mean()),
)
fcols = ["night", "crossing", "intersection", "two_wheel", "heavy"]
Xf = StandardScaler().fit_transform(feat[fcols])
sil = {}
for k in range(2, 7):
    km = KMeans(n_clusters=k, n_init=50, random_state=42).fit(Xf)
    sil[k] = silhouette_score(Xf, km.labels_)
S["silhouette"] = {int(k): round(float(v), 3) for k, v in sil.items()}
K = 4
km = KMeans(n_clusters=K, n_init=50, random_state=42).fit(Xf)
feat["cluster"] = km.labels_
prof = feat.groupby("cluster")[fcols].mean()
size = feat.groupby("cluster").size()
# 유형 이름: 전체 평균 대비 가장 두드러진(표준화 편차 최대) 특성으로 명명, 두드러진 특성이 없으면(<0.5σ) 생활가로형
gm = feat[fcols].mean()
names = {"night": "야간 횡단형", "crossing": "횡단보도형", "intersection": "교차로 횡단형", "two_wheel": "이륜·PM형", "heavy": "간선 대형차형"}
lift = (prof - gm) / feat[fcols].std()
cl_name = {c: (names[lift.loc[c].idxmax()] if lift.loc[c].max() >= 0.5 else "시장·생활가로형") for c in prof.index}
feat["type"] = feat.cluster.map(cl_name)
prof.index = [cl_name[c] for c in prof.index]
prof["다발지 수"] = size.values
(prof[fcols] * 100).round(1).assign(다발지수=size.values).to_csv(TAB / "t3_hotspot_types.csv", encoding="utf-8-sig")
S["cluster_profile"] = (prof[fcols] * 100).round(1).assign(n=size.values).reset_index().rename(columns={"index": "type"}).to_dict("records")
hg = hg.merge(feat[["type"] + fcols], left_on="zoneCode", right_index=True, how="left")
hg["market"] = hg.zoneDetailNm.str.contains("시장|상가|상점가")
S["market_share_by_type"] = (hg.groupby("type").market.mean() * 100).round(0).to_dict()
S["n_market_hot"] = int(hg.market.sum())

# ---------- 7. 우선 지정 후보 점수 ----------
# 점수 = 사상자(정규화) 40% + 사망(정규화) 20% + 반복선정 20% + 실버존 거리(1km 상한) 20%
def mm(s):
    return (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else s * 0
hg["score"] = (0.4 * mm(hg.caltCnt) + 0.2 * mm(hg.dprsCnt) + 0.2 * (hg.repeat / 2)
               + 0.2 * np.clip(hg.d_silver, 0, 1000) / 1000) * 100
hg = hg.sort_values("score", ascending=False)
top = hg.head(10)[["zoneDetailNm", "caltCnt", "dprsCnt", "repeat", "d_silver", "type", "score"]].copy()
top["zoneDetailNm"] = top.zoneDetailNm.str.replace("서울 ", "", regex=False)
top["d_silver"] = top.d_silver.round(0).astype(int)
top["score"] = top.score.round(1)
top.to_csv(TAB / "t4_priority_top10.csv", index=False, encoding="utf-8-sig")
hg.drop(columns="geometry").to_csv(TAB / "t5_hotspots_2025_scored.csv", index=False, encoding="utf-8-sig")
S["top10"] = top.to_dict("records")

# 지도: 다발지(유형별 형태) + 노인보호구역 300m
fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.3), gridspec_kw={"wspace": 0.12, "width_ratios": [1.45, 1]})
ax = axes[0]
seoul.plot(ax=ax, color="#f3f2ef", edgecolor="white", linewidth=0.8)
silver.buffer(300).plot(ax=ax, color="#9ec5f4", alpha=0.55, linewidth=0)
silver.plot(ax=ax, color=C_OLD, markersize=1.2)
covered = hg[hg.d_silver <= 300]; uncovered = hg[hg.d_silver > 300]
uncovered.plot(ax=ax, color="#e34948", markersize=uncovered.caltCnt * 2.2, edgecolor="white", linewidth=0.6, zorder=3)
covered.plot(ax=ax, color="#1baf7a", markersize=covered.caltCnt * 2.2, edgecolor="white", linewidth=0.6, zorder=3)
for i, (_, rw) in enumerate(hg.head(10).iterrows()):
    ax.annotate(str(i + 1), (rw.geometry.x, rw.geometry.y), xytext=(3, 3), textcoords="offset points", fontsize=6, fontweight="bold", color=INK)
ax.set_axis_off(); ax.set_title("⑨ 노인 보행사고 다발지(2025 선정)와 실버존")
from matplotlib.lines import Line2D
lh = [Line2D([], [], marker="o", ls="", color="#e34948", markersize=5, label=f"보호구역 밖 다발지 ({len(uncovered)})"),
      Line2D([], [], marker="o", ls="", color="#1baf7a", markersize=5, label=f"보호구역 300m 내 다발지 ({len(covered)})"),
      Patch(color="#9ec5f4", label=f"노인보호구역 반경 300m ({len(silver)}개소)")]
ax.legend(handles=lh, frameon=False, fontsize=6, loc="lower left")
ax = axes[1]
ds = np.sort(hg.d_silver)
ax.step(ds, np.arange(1, len(ds) + 1) / len(ds) * 100, where="post", color=C_OLD, lw=2)
ax.axvline(300, color="#e34948", lw=0.9, ls="--"); ax.text(320, 8, "300m\n(보호구역 영향권)", fontsize=6.5, color="#e34948")
ax.set_xlim(0, 2000); ax.set_ylim(0, 102)
ax.set_xlabel("가장 가까운 노인보호구역까지 거리(m)"); ax.set_ylabel("누적 다발지 비율(%)")
ax.set_title("⑩ 다발지→가장 가까운 실버존 거리")
ax.grid(color="#efede8", lw=0.6); ax.set_axisbelow(True)
save(fig, "fig5_hotspot_map.png")

# 유형 프로필 히트맵
fig, ax = plt.subplots(figsize=(7.2, 1.9))
pv = (prof[fcols] * 100)
colnames = ["야간 비율", "횡단 중 비율", "교차로 비율", "이륜·자전거·PM", "화물·승합 등"]
ax.imshow(pv.values, cmap=ListedColormap(SEQ), aspect="auto", vmin=0, vmax=100)
for i in range(pv.shape[0]):
    for j in range(pv.shape[1]):
        v = pv.values[i, j]
        ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=7.5, color="white" if v > 55 else INK)
ax.set_xticks(range(len(colnames)), colnames); ax.set_yticks(range(len(pv)), [f"{n} ({s}곳)" for n, s in zip(pv.index, size.values)])
ax.set_title("⑪ K-평균 군집으로 본 다발지 4가지 유형 (각 유형 평균 사고 구성)")
for s in ax.spines.values(): s.set_visible(False)
ax.tick_params(length=0)
save(fig, "fig6_types.png")

json.dump(S, open(ROOT / "outputs" / "summary.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(S, ensure_ascii=False, indent=1, default=str))
