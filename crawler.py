import requests
import pandas as pd
import time
import math  # 페이지 계산용

# 1. 설정
url = "https://www.hyundai.com/wsvc/kr/front/biz/serviceNetwork.list.do"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.hyundai.com/kr/ko/service-membership/service-network/service-reservation-search",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest"
}

regions = {
    "서울": "서울특별시",
    "경기": "경기도",
    "인천": "인천광역시"
}

all_data = []

print("🔧 전체 데이터 수집 시작")

for region_alias, region_full_name in regions.items():
    print(f"\n🔄 [{region_alias}] 수집 시작")

    current_page = 1
    total_pages = 1  # 일단 1로 시작해서 첫 요청 후 업데이트

    while current_page <= total_pages:
        # Payload 설정 (pageNo가 계속 변함)
        payload = {
            "pageNo": current_page,
            "searchWord": "",
            "snGubunListSearch": "",
            "selectBoxCity": region_full_name,
            "selectBoxCitySearch": region_full_name,
            "selectBoxTownShipSearch": "",
            "asnCd": ""
        }

        try:
            response = requests.post(url, data=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                result_block = data.get('data', {})
                items = result_block.get('result', [])

                # 첫 페이지일 때만 전체 개수 확인해서 목표 페이지 설정
                if current_page == 1:
                    total_count = result_block.get('totalCount', 0)
                    # 10개씩 보여주니까, 총 페이지 = (전체개수 / 10) 올림 처리
                    total_pages = math.ceil(total_count / 10)
                    print(f"   📊 총 {total_count}개 발견 (약 {total_pages} 페이지 예상)")

                if not items:  # 데이터가 없으면 중단
                    break

                for item in items:
                    # 좌표 보정
                    val1 = float(item.get('mapLaeVal', 0) or 0)
                    val2 = float(item.get('mapLoeVal', 0) or 0)

                    if val1 > 100:
                        lon, lat = val1, val2
                    else:
                        lon, lat = val2, val1
                    # f12 개발자 도구 까서 확인한 것 !
                    info = {
                        'region': region_alias,
                        'name': item.get('asnNm'),
                        'type': item.get('apimCeqPlntNm'),
                        'address': item.get('pbzAdrSbc'),
                        'phone': item.get('repnTn', '').strip(),
                        'latitude': lat,
                        'longitude': lon,
                        'is_ev': 1 if item.get('spcialSrvC002') == 'Y' else 0,
                        'is_excellent': 1 if item.get('xclFirmYn') == 'Y' else 0
                    }
                    all_data.append(info)

                # 진행 상황 출력 (너무 자주 찍으면 지저분하니 5페이지마다)
                if current_page % 5 == 0:
                    print(f"      ▶ {current_page}/{total_pages} 페이지 수집 중")

                current_page += 1  # 다음 페이지로

            else:
                print(f"      ❌ 요청 실패: {response.status_code}")
                break

        except Exception as e:
            print(f"      ⚠️ 에러 발생: {e}")
            break

        time.sleep(0.2)  # 서버 부하 방지

    print(f"   ✅ [{region_alias}] 완료.")

# 결과 저장
print("=" * 50)
df = pd.DataFrame(all_data)
print(f"💾 최종 수집 결과: 총 {len(df)}개")
print(df.groupby('region')['name'].count())  # 지역별 개수 확인
print(df.head())

# CSV 저장
df.to_csv("bluehands_final_all.csv", index=False, encoding="utf-8-sig")
print("\n 'bluehands_final_all.csv' 파일로 저장했습니다.")