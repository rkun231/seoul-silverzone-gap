/*
 * TAAS 원자료 수집 스크립트 (브라우저 콘솔용)
 * TAAS 자료는 이용약관 제14조(정보의 배포 제한)에 따라 이 저장소에 포함하지 않았습니다.
 * 재현하려면 https://taas.koroad.or.kr/gis/mcm/mcl/initMap.do?menuId=GIS_GMP_STS_RSN 을 열고
 * 개발자도구 콘솔에 이 파일 내용을 붙여넣은 뒤 `await collectAll()`을 실행하세요.
 * 화면의 [사고분석]·[다발지분석]·[보호구역사고조회] 메뉴가 쓰는 조회 기능을 그대로 사용합니다.
 * 결과 CSV 6개가 내려받아지면 data/raw/ 에 넣으세요.  (출처: 한국도로교통공단 TAAS)
 */
const toCSV = (rows, cols) => '﻿' + cols.join(',') + '\n' + rows.map(r => cols.map(c => {
  let v = r[c]; if (v === null || v === undefined) return ''; v = String(v).trim();
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(',')).join('\n');
const save = (name, text) => { const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' })); a.download = name; a.click(); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 사고분석 화면의 검색을 실행하고 응답(JSON)을 가로챔
async function searchAccidents(year, code) {
  const $ = window.jQuery; let resp = null;
  const o = XMLHttpRequest.prototype.open, s = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return o.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) { if (/selectAccidentInfo/.test(this.__u)) this.addEventListener('load', () => { resp = this.responseText; }); return s.apply(this, arguments); };
  $('#ptsRafYearStart').val(String(year)).trigger('change'); await sleep(300);
  $('#ptsRafYearEnd').val(String(year)).trigger('change');
  $('#ptsRafSido').val('11').trigger('change'); await sleep(800);
  $('#ptsRafSigungu').val('01').trigger('change');                 // 서울 전체
  document.querySelectorAll('input[name=ACDNT_GAE_CODE]').forEach((c, i) => { if (i < 4) c.checked = true; }); // 사망·중상·경상·부상신고
  $('#ptsRafSimpleCondition').val(code).trigger('change');           // 42=노인 보행자 사고, 44=보행 어린이 사고
  let p = document.getElementById('ptsRafSimpleCondition'), btn = null;
  while (p && !btn) { p = p.parentElement; btn = [...p.querySelectorAll('a')].find(a => a.textContent.trim() === '검색'); }
  btn.click();
  for (let i = 0; i < 60 && !resp; i++) await sleep(500);
  XMLHttpRequest.prototype.open = o; XMLHttpRequest.prototype.send = s;
  return JSON.parse(resp).resultValue.accidentInfoList;
}

const ACC_COLS = ['acdnt_no','acdnt_year','acdnt_dd_dc','dfk_dc','tmzon_div_1_dc','occrrnc_time_dc','legaldong_code','legaldong_name','acdnt_dc','lrg_violt_1_dc','wether_sttus_dc','road_stle_dc','rdse_sttus_dc','acdnt_gae_dc','dprs_cnt','sep_cnt','slp_cnt','inj_aplcnt_cnt','wrngdo_vhcle_asort_dc','acdnt_age_1_dc','sexdstn_div_1_dc','dmge_vhcle_asort_dc','injury_dgree_2_dc','acdnt_age_2_dc','sexdstn_div_2_dc','acdnt_pos','xCrdnt','yCrdnt'];

async function collectAll() {
  // 1) 노인·어린이 보행사고 2021~2025
  for (const [code, tag] of [['42', 'elderly_ped'], ['44', 'child_ped']]) {
    let all = [];
    for (const y of [2021, 2022, 2023, 2024, 2025]) all = all.concat(await searchAccidents(y, code));
    save(`taas_seoul_${tag}_accidents_2021_2025.csv`, toCSV(all, ACC_COLS));
  }
  // 2) 사고다발지역(보행노인 2023~25년 선정, 보행어린이 2024~25년 선정)
  const base = '/gis/tas/paf/'; const zones = [], accs = [];
  const groups = [['2026121','보행노인','25년'],['2025076','보행노인','24년'],['2024044','보행노인','23년'],['2026124','보행어린이','25년'],['2025108','보행어린이','24년']];
  for (const [gid, kind, yr] of groups) {
    const z = await fetch(`${base}selectPartZoneInfo.do?groupId=${gid}&zoneCode=11%25&pageIndex=1&zoneYn=false`).then(r => r.json());
    const a = await fetch(`${base}selectPartAccidentInfo.do?groupId=${gid}&zoneCode=11%25&spatialCriteria=&pageIndex=1&zoneYn=false&isExcel=false`).then(r => r.json());
    z.resultValue.partAccidentFindInfoList.forEach(r => zones.push({ groupId: gid, kind, selYear: yr, ...r }));
    a.resultValue.accidentInfoList.forEach(r => accs.push({ groupId: gid, kind, selYear: yr, ...r }));
  }
  save('taas_seoul_ped_hotspot_zones.csv', toCSV(zones, ['groupId','kind','selYear','zoneCode','zoneNm','zoneDetailNm','occrCnt','caltCnt','dprsCnt','sepCnt','slpCnt','injpCnt','xCrdnt','yCrdnt']));
  save('taas_seoul_ped_hotspot_accidents.csv', toCSV(accs, ['groupId','kind','selYear','acdnt_no','acdnt_dd_dc','dfk_dc','tmzon_div_1_dc','occrrnc_time_dc','legaldong_name','acdnt_dc','lrg_violt_1_dc','road_stle_dc','acdnt_gae_dc','dprs_cnt','sep_cnt','slp_cnt','wrngdo_vhcle_asort_dc','acdnt_age_1_dc','acdnt_age_2_dc','sexdstn_div_2_dc','acdnt_pos','xCrdnt','yCrdnt']));
  // 3) 서울 어린이·노인 보호구역 지정 대상시설과 구역 폴리곤
  const r = await fetch('/gis/pae/pta/selectPrtcAreaTrgetSpotList.do?laddrEmd=11%25&fcltyTy=1%7C2&pageIndex=1').then(r => r.json());
  const pts = r.resultValue.prtcAreaAssignInfoList.map(x => ({ ...x.prtcAreaAssignVo, x: x.prtcAreaAssignGeoVo.xCrd, y: x.prtcAreaAssignGeoVo.yCrd }));
  const polys = r.resultValue.prtcAreaSnctInfoList.map(x => ({ ...x.prtcAreaSnctVo, wkt: x.prtcAreaSnctGeoVo.geomToText }));
  save('taas_seoul_protection_zones_points.csv', toCSV(pts, ['serial','fcltyTy','fcltyNm','fcltyDetailTy','fcltyDetailTyNm','assignDt','laddrEmd','addr','laddr','orgPol','useYn','snctCnt','x','y']));
  save('taas_seoul_protection_zones_polygons.csv', toCSV(polys, ['serial','snctSeq','useYn','wkt']));
}
