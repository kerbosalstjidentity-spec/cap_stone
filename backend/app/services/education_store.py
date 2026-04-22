"""교육 프로그램 인메모리 저장소 — 코스, 챌린지, 배지, 퀴즈 점수."""

from collections import defaultdict
from datetime import datetime

from app.schemas.education import (
    Badge,
    Challenge,
    ChallengeEnrollment,
    ChallengeStatus,
    Course,
    CourseProgress,
    CourseStep,
    EduLevel,
)


# ── 코스 콘텐츠 (정적) ───────────────────────────────────────

COURSES: dict[str, Course] = {}

def _init_courses() -> None:
    """레벨별 교육 코스 초기화."""

    # Level 1: 기초반
    COURSES["L1_C1"] = Course(
        course_id="L1_C1", level=EduLevel.BEGINNER,
        title="수입 vs 지출 — 첫 가계부 만들기",
        description="자신의 수입과 지출 흐름을 파악하고, 간단한 가계부를 작성하는 방법을 배웁니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="수입 파악하기",
                content="월급, 부수입 등 모든 수입원을 정리해봅시다. 세후 실수령액 기준으로 계산하는 것이 중요합니다.",
                tip="급여명세서를 확인하면 정확한 실수령액을 알 수 있습니다."),
            CourseStep(step=2, title="지출 분류 이해하기",
                content="지출은 크게 고정지출(월세, 통신비, 보험)과 변동지출(식비, 쇼핑, 여가)로 나뉩니다. 내 소비 데이터에서 각 카테고리를 확인해봅시다.",
                tip="고정지출은 매월 비슷하고, 변동지출은 노력으로 줄일 수 있습니다.",
                interactive="category_chart"),
            CourseStep(step=3, title="데모 데이터로 가계부 실습",
                content="시스템에서 제공하는 데모 데이터를 생성하고, 대시보드에서 내 소비 현황을 확인해봅시다. 카테고리별 비율과 월별 추이를 살펴보세요.",
                tip="대시보드의 '데모 데이터 생성' 버튼으로 3개월치 데이터를 만들 수 있습니다.",
                interactive="seed_demo"),
            CourseStep(step=4, title="내 소비 요약 읽기",
                content="대시보드에서 총 지출, 건당 평균, 최대 지출, 주 소비 카테고리를 확인합니다. 이 숫자들이 무엇을 의미하는지 이해하는 것이 재무 관리의 첫걸음입니다.",
                tip="건당 평균이 높다면 큰 금액 소비가 많다는 뜻, 거래 건수가 많다면 소액 소비가 빈번하다는 뜻입니다."),
        ],
    )
    COURSES["L1_C2"] = Course(
        course_id="L1_C2", level=EduLevel.BEGINNER,
        title="카테고리별 소비 비중 이해하기",
        description="내 소비가 어느 카테고리에 집중되어 있는지 파악하고, 건강한 소비 비율을 알아봅니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="카테고리 분류 체계",
                content="소비는 식비, 쇼핑, 교통, 여가, 교육, 의료, 주거, 공과금, 금융, 여행 등으로 분류됩니다. 각 카테고리의 특성을 이해합시다.",
                tip="같은 '카페'라도 업무용이면 교통/기타, 여가용이면 식비로 분류할 수 있습니다."),
            CourseStep(step=2, title="내 카테고리 비율 확인",
                content="대시보드의 도넛 차트에서 각 카테고리 비율을 확인해봅시다. 특정 카테고리가 30%를 넘으면 편중 신호입니다.",
                tip="주거비(월세)가 높은 것은 자연스러운 것이지만, 쇼핑이나 식비가 30%를 넘으면 주의가 필요합니다.",
                interactive="category_chart"),
            CourseStep(step=3, title="이상적인 소비 비율",
                content="일반적으로 권장되는 소비 비율: 주거 30% 이하, 식비 15~20%, 교통 10%, 저축/투자 20% 이상. 물론 개인 상황에 따라 다를 수 있습니다.",
                tip="사회 초년생은 저축 비율을 최소 10%부터 시작해서 점진적으로 늘리는 것을 추천합니다."),
            CourseStep(step=4, title="편중 카테고리 개선 계획",
                content="편중된 카테고리를 확인했다면, 구체적인 절감 목표를 세워봅시다. '식비 20% 줄이기'보다 '주 3회 도시락 싸기'처럼 행동 기반 목표가 효과적입니다.",
                tip="한 번에 크게 줄이기보다 매주 조금씩 줄이는 것이 지속 가능합니다."),
        ],
    )
    COURSES["L1_C3"] = Course(
        course_id="L1_C3", level=EduLevel.BEGINNER,
        title="고정지출 vs 변동지출 구분법",
        description="매월 반복되는 고정지출과 조절 가능한 변동지출을 구분하여 관리하는 방법을 배웁니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="고정지출이란?",
                content="매월 일정하게 나가는 지출입니다. 월세, 통신비, 보험료, 구독 서비스 등이 해당됩니다. 내 데이터에서 주거(housing), 공과금(utilities), 금융(finance) 카테고리를 확인해봅시다.",
                tip="고정지출은 한 번 줄이면 매월 자동으로 절약되는 효과가 있습니다."),
            CourseStep(step=2, title="변동지출이란?",
                content="매월 금액이 달라지는 지출입니다. 식비, 쇼핑, 여가, 교통비 등이 대표적입니다. 월별 추이 차트에서 변동이 큰 카테고리를 찾아봅시다.",
                tip="변동지출은 습관 변화로 가장 빠르게 줄일 수 있는 영역입니다.",
                interactive="trend_chart"),
            CourseStep(step=3, title="고정지출 점검 체크리스트",
                content="1) 안 쓰는 구독 서비스 해지 2) 통신비 요금제 재검토 3) 보험료 중복 확인 4) 관리비 절감 방법 탐색. 이 4가지만 점검해도 월 5~10만원 절약이 가능합니다.",
                tip="넷플릭스, 스포티파이 등 구독 서비스를 모두 합산하면 의외로 큰 금액일 수 있습니다."),
            CourseStep(step=4, title="변동지출 통제 전략",
                content="주 단위 예산 설정, 현금 봉투법, 소비 전 24시간 대기 규칙 등을 활용할 수 있습니다. 전략 제안 페이지에서 맞춤 추천을 확인해봅시다.",
                tip="변동지출은 '얼마나'보다 '얼마나 자주'가 더 중요합니다. 소비 빈도를 줄이는 것이 핵심입니다.",
                interactive="strategy_recommend"),
        ],
    )
    COURSES["L1_C4"] = Course(
        course_id="L1_C4", level=EduLevel.BEGINNER,
        title="50/30/20 법칙 적용해보기",
        description="전 세계적으로 검증된 예산 배분 법칙을 내 상황에 맞게 적용해봅니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="50/30/20 법칙이란?",
                content="세후 수입의 50%는 필수지출(주거, 식비, 교통, 공과금), 30%는 원하는 것(쇼핑, 여가, 여행), 20%는 저축/투자에 배분하는 법칙입니다.",
                tip="이 비율은 절대적인 것이 아니라 가이드라인입니다. 사회 초년생은 60/20/20부터 시작해도 좋습니다."),
            CourseStep(step=2, title="내 현재 비율 계산",
                content="내 소비 데이터를 기준으로 필수/선택/저축 비율을 계산해봅시다. 식비+교통+주거+공과금 = 필수, 쇼핑+여가+여행 = 선택, 금융 = 저축으로 대략 분류합니다.",
                tip="진단 페이지에서 자동으로 계산된 비율을 확인할 수 있습니다.",
                interactive="diagnosis"),
            CourseStep(step=3, title="예산 설정 실습",
                content="전략 제안 페이지에서 카테고리별 월 예산을 직접 설정해봅시다. 50/30/20 비율에 맞춰 각 카테고리에 금액을 배분합니다.",
                tip="처음에는 현재 소비의 90% 수준으로 예산을 잡고, 점진적으로 목표 비율에 접근하세요.",
                interactive="budget_api"),
            CourseStep(step=4, title="예산 추적과 조정",
                content="예산을 설정한 후에는 정기적으로 실제 지출과 비교해야 합니다. 절약 분석 페이지에서 예산 초과 항목을 확인하고 다음 달 예산을 조정합시다.",
                tip="예산 초과가 2개월 연속되면 예산이 비현실적일 수 있습니다. 조금 올려서 달성 가능한 목표를 세우세요."),
        ],
    )

    # Level 2: 중급반
    COURSES["L2_C1"] = Course(
        course_id="L2_C1", level=EduLevel.INTERMEDIATE,
        title="내 소비 패턴 분석 결과 읽기",
        description="K-Means 군집 분석 결과를 이해하고 내 소비 유형의 특징과 개선 방향을 파악합니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="소비 유형 분류란?",
                content="K-Means 알고리즘은 소비 패턴이 비슷한 사람들을 그룹으로 묶습니다. 절약형, 균형형, 소비형, 투자형 — 각 유형의 특징을 알아봅시다.",
                tip="소비형이라고 나쁜 것이 아닙니다. 현재 상태를 정확히 아는 것이 개선의 시작입니다."),
            CourseStep(step=2, title="내 유형 결과 확인",
                content="패턴 분석 페이지에서 레이더 차트를 확인합니다. 각 축은 카테고리별 소비 비중을 나타냅니다. 어디가 돌출되어 있는지 살펴보세요.",
                tip="레이더 차트가 원형에 가까울수록 균형 잡힌 소비입니다.",
                interactive="pattern_analysis"),
            CourseStep(step=3, title="유형별 특징과 주의점",
                content="절약형: 필요한 곳에 투자 부족 가능성 / 균형형: 안정적이나 저축률 확인 필요 / 소비형: 충동소비 패턴 점검 / 투자형: 단기 유동성 확보 필요.",
                tip="한 유형이 영원하지 않습니다. 3개월마다 재분석하면 변화를 추적할 수 있습니다."),
            CourseStep(step=4, title="유형 개선 목표 설정",
                content="현재 유형에서 목표 유형으로 이동하기 위한 구체적 계획을 세웁니다. 예: 소비형 → 균형형으로 전환하려면 쇼핑 비중 10% 감축 필요.",
                tip="급격한 변화보다 한 카테고리씩 집중 개선하는 것이 효과적입니다."),
        ],
    )
    COURSES["L2_C2"] = Course(
        course_id="L2_C2", level=EduLevel.INTERMEDIATE,
        title="라테 팩터 — 소액 누수 찾기",
        description="매일 반복되는 소액 지출이 어떻게 큰 금액이 되는지 파악하고 누수를 막는 법을 배웁니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="라테 팩터란?",
                content="매일 5,000원짜리 커피 = 월 15만원 = 연 180만원. 작은 소비가 모이면 큰 금액이 됩니다. 이를 '라테 팩터'라고 합니다.",
                tip="라테 팩터는 커피만이 아닙니다. 편의점 간식, 배달앱 소액 주문, 앱 내 결제 등도 포함됩니다."),
            CourseStep(step=2, title="내 소액 소비 패턴 분석",
                content="이상 탐지(Isolation Forest)는 큰 이상 거래뿐 아니라 소액 빈번 거래도 패턴을 찾아냅니다. 카테고리별 건당 평균과 빈도를 비교해봅시다.",
                tip="건당 평균은 낮지만 건수가 많은 카테고리가 라테 팩터 후보입니다.",
                interactive="anomaly_analysis"),
            CourseStep(step=3, title="소액 누수 계산기",
                content="시뮬레이션에서 특정 카테고리를 20% 줄이면 연간 얼마나 절약되는지 직접 계산해봅시다.",
                tip="'매일 3,000원'이 별것 아닌 것 같지만, 투자 수익률 5% 기준으로 10년 후 약 1,400만원입니다.",
                interactive="savings_simulate"),
            CourseStep(step=4, title="소액 누수 막기 실천법",
                content="1) 주 단위 용돈 설정 2) 현금 카드 사용 3) 소비 전 메모 습관 4) 대안 찾기 (텀블러, 집밥). 챌린지 기능으로 2주간 커피 절약에 도전해봅시다.",
                tip="처음부터 0원 목표보다 '횟수 반으로 줄이기'가 현실적입니다."),
        ],
    )
    COURSES["L2_C3"] = Course(
        course_id="L2_C3", level=EduLevel.INTERMEDIATE,
        title="다음 달 지출 예측과 선제 대응",
        description="LSTM 예측 결과를 활용하여 다음 달 지출을 미리 예상하고 대비하는 방법을 배웁니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="지출 예측이 필요한 이유",
                content="과거 패턴을 분석하면 다음 달 지출을 예측할 수 있습니다. 미리 알면 예산을 조정하고 과소비를 예방할 수 있습니다.",
                tip="예측은 100% 정확하지 않지만, 방향성을 아는 것만으로도 큰 도움이 됩니다."),
            CourseStep(step=2, title="LSTM 예측 결과 읽기",
                content="패턴 분석 페이지에서 예측 결과를 확인합니다. 예측 총액과 카테고리별 예측을 비교하고, 신뢰도(confidence)를 참고하세요.",
                tip="신뢰도가 0.7 이상이면 꽤 신뢰할 수 있는 예측입니다. 0.5 미만이면 데이터가 부족합니다.",
                interactive="forecast_analysis"),
            CourseStep(step=3, title="예측 기반 예산 조정",
                content="예측 금액이 현재 예산을 초과할 것으로 보이면, 미리 카테고리별 예산을 재배분합니다. 특히 증가 예상 카테고리에 주목하세요.",
                tip="명절, 여행 등 특별 지출이 예상되면 미리 별도 예산을 편성하세요."),
            CourseStep(step=4, title="선제 대응 전략 수립",
                content="예측 결과를 바탕으로 '이번 달 가장 주의할 카테고리'를 정하고, 구체적 행동 계획을 세웁니다. 전략 제안에서 맞춤 추천도 확인해봅시다.",
                tip="예측보다 10% 적게 쓰는 것을 목표로 하면 자연스럽게 저축이 늘어납니다.",
                interactive="strategy_recommend"),
        ],
    )
    COURSES["L2_C4"] = Course(
        course_id="L2_C4", level=EduLevel.INTERMEDIATE,
        title="나만의 절약 전략 세우기",
        description="분석 결과를 종합하여 나에게 맞는 맞춤형 절약 전략을 설계합니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="내 절약 가능 영역 파악",
                content="전략 제안 페이지에서 '절약 가능 항목'을 확인합니다. 시스템이 분석한 절약 가능 금액과 이유를 살펴보세요.",
                tip="절약 가능 금액이 가장 큰 카테고리부터 우선 공략하세요.",
                interactive="strategy_recommend"),
            CourseStep(step=2, title="SMART 목표 설정",
                content="S(구체적): '식비 줄이기' → '주 3회 도시락' / M(측정가능): 월 20만원 절약 / A(달성가능): 현실적 수준 / R(관련성): 저축 목표와 연결 / T(기한): 이번 달 내.",
                tip="목표를 글로 적어두면 달성률이 42% 높아진다는 연구 결과가 있습니다."),
            CourseStep(step=3, title="자동화 전략",
                content="매월 급여일에 자동 이체(적금, 투자), 카드 한도 설정, 알림 설정 등 '의지력에 의존하지 않는' 시스템을 구축합니다.",
                tip="저축을 먼저 하고 남은 돈으로 소비하는 '선저축 후소비'가 가장 효과적입니다."),
            CourseStep(step=4, title="월간 리뷰 루틴 만들기",
                content="매월 말 15분만 투자하여 이번 달 소비를 점검합니다. 대시보드 → 전월 비교 → 전략 조정의 사이클을 반복하면 3개월 후 눈에 띄는 변화가 나타납니다.",
                tip="리뷰를 습관으로 만드세요. 캘린더에 매월 같은 날을 '재무 점검일'로 지정하세요."),
        ],
    )

    # Level 3: 고급반
    COURSES["L3_C1"] = Course(
        course_id="L3_C1", level=EduLevel.ADVANCED,
        title="금융 사기의 유형과 실제 사례",
        description="실제 데이터 기반으로 금융 사기의 주요 유형과 패턴을 학습합니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="금융 사기의 현황",
                content="연간 금융 사기 피해액은 수천억 원에 달합니다. 카드 도용, 피싱, 스미싱, 보이스피싱 등 다양한 유형이 있으며, 사회 초년생이 특히 취약합니다.",
                tip="20~30대 피해 비율이 전체의 35%로 가장 높습니다. '나는 괜찮겠지'라는 생각이 가장 위험합니다."),
            CourseStep(step=2, title="카드 사기의 주요 패턴",
                content="1) 소액 테스트 후 고액 결제 2) 새벽 시간대 해외 결제 3) 단시간 내 다수 결제(분할 결제) 4) 처음 보는 가맹점. 사기 탐지 시스템은 이런 패턴을 자동으로 감지합니다.",
                tip="이 패턴들은 실제 28만건 이상의 거래 데이터 분석에서 도출된 것입니다."),
            CourseStep(step=3, title="피싱/스미싱 사례 분석",
                content="택배 사칭 문자, 금융기관 사칭 전화, 가짜 결제 알림 등 최신 수법을 분석합니다. 실제 사례를 보며 어떤 점이 수상한지 찾아봅시다.",
                tip="금융기관은 절대 문자/전화로 비밀번호나 OTP를 요구하지 않습니다."),
            CourseStep(step=4, title="사기 통계로 보는 위험 신호",
                content="Isolation Forest와 규칙 엔진이 탐지하는 핵심 특성: 금액 이상, 시간대 이상, 빈도 이상, 위치 이상. 각 특성이 왜 중요한지 데이터로 확인합니다.",
                tip="보안 교육 페이지에서 실제 사기 거래 퀴즈를 풀어보세요.",
                interactive="fraud_quiz"),
        ],
    )
    COURSES["L3_C2"] = Course(
        course_id="L3_C2", level=EduLevel.ADVANCED,
        title="내 거래의 사기 위험도 이해하기",
        description="사기 탐지 시스템의 스코어링 방식을 이해하고 내 거래 안전도를 점검합니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="사기 스코어란?",
                content="모든 거래에 0~1 사이의 사기 확률 점수가 매겨집니다. 0.35 미만은 정상(PASS), 0.35~0.95는 검토 필요(REVIEW), 0.95 이상은 차단(BLOCK).",
                tip="REVIEW는 '의심'이지 '사기 확정'이 아닙니다. 본인 확인으로 해결할 수 있습니다."),
            CourseStep(step=2, title="규칙 엔진의 8가지 규칙",
                content="금액 차단(500만↑), 금액 검토(100만↑), 심야 거래(2~5시+50만↑), 속도 탐지(10분 내 3건↑), 분할 거래(1만↓+1분 내 5건↑), 해외IP, 금액 급등(평균 5배↑), 신규 가맹점(20만↑).",
                tip="보안 교육의 시뮬레이터에서 각 규칙이 어떻게 작동하는지 직접 체험해보세요.",
                interactive="fraud_simulate"),
            CourseStep(step=3, title="내 거래 패턴 안전도 점검",
                content="이상 탐지 결과에서 내 거래 중 이상으로 분류된 건을 확인합니다. 본인 거래인데 이상으로 분류된 것은 왜인지, 어떤 패턴이 감지된 것인지 이해합니다.",
                tip="해외여행 전 카드사에 여행 일정을 알리면 정상 거래가 차단되는 것을 방지할 수 있습니다.",
                interactive="anomaly_analysis"),
            CourseStep(step=4, title="안전한 거래 습관",
                content="1) 결제 알림 즉시 확인 2) 해외 결제 차단 기본 설정 3) 카드 분실 시 즉시 정지 4) 온라인 결제 시 가상카드 번호 사용 5) 정기적 거래 내역 확인.",
                tip="카드사 앱에서 해외 결제 차단, 온라인 결제 한도 설정을 지금 바로 해보세요."),
        ],
    )
    COURSES["L3_C3"] = Course(
        course_id="L3_C3", level=EduLevel.ADVANCED,
        title="의심 거래 시 대처법",
        description="의심 거래를 발견했을 때의 단계별 대응 방법과 Step-up 인증 체험.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="의심 거래 발견 시 즉시 행동",
                content="1단계: 카드 즉시 정지(앱 또는 전화) 2단계: 카드사 고객센터 신고 3단계: 경찰 사이버수사대 신고(182) 4단계: 금감원 상담(1332).",
                tip="카드 정지는 앱에서 30초면 됩니다. 의심되면 일단 정지하고 확인하세요."),
            CourseStep(step=2, title="Step-up 인증이란?",
                content="의심 거래가 감지되면 본인 확인을 요청하는 추가 인증입니다. 푸시 알림으로 '본인 거래 맞으신가요?' 확인을 받습니다. 승인하면 거래 진행, 거부하면 차단됩니다.",
                tip="Step-up 인증 요청이 왔는데 본인 거래가 아니라면, 반드시 '거부'를 누르고 카드사에 신고하세요."),
            CourseStep(step=3, title="피해 발생 시 구제 절차",
                content="부정 사용 신고 → 카드사 조사(보통 7~14일) → 일시적 임시 환불 → 조사 완료 후 최종 환불. 신고가 빠를수록 피해 구제율이 높습니다.",
                tip="거래 발생 후 60일 이내에 신고해야 보상받을 수 있습니다."),
            CourseStep(step=4, title="예방이 최선의 대책",
                content="사후 대처보다 예방이 중요합니다. 정기적 비밀번호 변경, 2단계 인증 설정, 공용 Wi-Fi에서 결제 자제, 출처 불명 링크 클릭 금지.",
                tip="비밀번호는 최소 3개월마다 변경하고, 사이트마다 다른 비밀번호를 사용하세요."),
        ],
    )
    COURSES["L3_C4"] = Course(
        course_id="L3_C4", level=EduLevel.ADVANCED,
        title="안전한 결제 습관 체크리스트",
        description="행동 시그널 분석 결과를 바탕으로 자신의 디지털 보안 습관을 점검합니다.",
        total_steps=4,
        steps=[
            CourseStep(step=1, title="행동 시그널이란?",
                content="사기 탐지 시스템은 마우스 움직임, 입력 속도, 탭 전환 빈도, VPN/TOR 사용 여부 등 행동 패턴도 분석합니다. 봇과 사람의 행동은 명확히 다릅니다.",
                tip="너무 빠른 폼 입력, 복사-붙여넣기 반복, 비정상적 마우스 패턴은 의심 신호입니다."),
            CourseStep(step=2, title="디지털 보안 습관 자가 진단",
                content="체크리스트: □ 2단계 인증 사용 □ 비밀번호 관리자 사용 □ OS/앱 최신 업데이트 □ 공용 Wi-Fi 결제 자제 □ 카드 알림 설정 □ 정기 거래 내역 확인.",
                tip="6개 중 4개 이상 체크하면 양호, 3개 이하면 즉시 개선이 필요합니다."),
            CourseStep(step=3, title="피싱 구별 훈련",
                content="보안 교육 페이지의 퀴즈에서 피싱/정상 거래 구별 훈련을 합니다. 실제 패턴에 기반한 문제로 판별 능력을 키웁니다.",
                tip="URL을 항상 직접 확인하세요. 'bank.com'과 'bank-secure.com'은 완전히 다른 사이트입니다.",
                interactive="fraud_quiz"),
            CourseStep(step=4, title="종합 보안 점수 확인",
                content="퀴즈 성적, 디지털 보안 습관 점수, 거래 패턴 안전도를 종합한 보안 점수를 확인합니다. 목표: 80점 이상 유지.",
                tip="보안 점수가 낮다면 이 코스를 다시 복습하고, 체크리스트 항목을 하나씩 실천해보세요.",
                interactive="security_score"),
        ],
    )


_init_courses()


# ── 챌린지 정의 (정적) ────────────────────────────────────────

CHALLENGES: dict[str, Challenge] = {
    "coffee_save": Challenge(
        challenge_id="coffee_save",
        name="커피 절약 챌린지",
        description="2주간 카페 소비를 50% 줄여보세요",
        duration_days=14,
        target_metric="food_cafe_reduction",
        target_description="식비 중 카페 관련 소비 50% 절감",
        target_value=50.0,
        badge_name="라테팩터 마스터",
        badge_icon="coffee",
    ),
    "budget_keeper": Challenge(
        challenge_id="budget_keeper",
        name="예산 지키기 챌린지",
        description="1개월간 설정한 예산을 초과하지 않기",
        duration_days=30,
        target_metric="budget_compliance",
        target_description="월 예산 대비 100% 이하 유지",
        target_value=100.0,
        badge_name="예산 수호자",
        badge_icon="shield",
    ),
    "zero_spend": Challenge(
        challenge_id="zero_spend",
        name="무지출 데이 챌린지",
        description="1주일 중 최소 2일 무지출 달성하기",
        duration_days=7,
        target_metric="zero_spend_days",
        target_description="7일 중 2일 이상 0원 소비",
        target_value=2.0,
        badge_name="절약왕",
        badge_icon="star",
    ),
    "fraud_quiz_master": Challenge(
        challenge_id="fraud_quiz_master",
        name="사기 탐지 퀴즈 마스터",
        description="사기 탐지 퀴즈 10문제 연속 정답",
        duration_days=30,
        target_metric="fraud_quiz_streak",
        target_description="퀴즈 연속 정답 10회 달성",
        target_value=10.0,
        badge_name="보안 전문가",
        badge_icon="lock",
    ),
    "type_change": Challenge(
        challenge_id="type_change",
        name="소비 유형 개선 챌린지",
        description="3개월 내 소비 유형 변화 달성",
        duration_days=90,
        target_metric="cluster_change",
        target_description="K-Means 군집 유형 변화 (예: 소비형 → 균형형)",
        target_value=1.0,
        badge_name="습관 혁신가",
        badge_icon="refresh",
    ),
}


# ── 소비 습관 퀴즈 문제 (정적) ────────────────────────────────

SPENDING_QUIZ_BANK = [
    {
        "id": "SQ01", "category": "budgeting",
        "question": "50/30/20 법칙에서 '20'은 무엇에 배분하는 비율인가요?",
        "options": ["필수 지출", "원하는 것", "저축/투자", "비상금"],
        "correct": "저축/투자",
        "explanation": "50%는 필수지출(주거, 식비 등), 30%는 원하는 것(여가, 쇼핑 등), 20%는 저축과 투자에 배분합니다.",
    },
    {
        "id": "SQ02", "category": "saving",
        "question": "매일 5,000원을 절약하면 1년간 얼마를 모을 수 있나요?",
        "options": ["약 90만원", "약 130만원", "약 180만원", "약 250만원"],
        "correct": "약 180만원",
        "explanation": "5,000원 × 365일 = 1,825,000원. 이것이 '라테 팩터'의 힘입니다.",
    },
    {
        "id": "SQ03", "category": "budgeting",
        "question": "'선저축 후소비' 방법으로 가장 적절한 것은?",
        "options": ["월말에 남은 돈 저축", "급여일에 자동이체로 저축 먼저", "보너스만 저축", "카드 포인트로 저축"],
        "correct": "급여일에 자동이체로 저축 먼저",
        "explanation": "급여가 들어오면 즉시 목표 금액을 저축 계좌로 자동이체하고, 남은 돈으로 생활하는 방식이 가장 효과적입니다.",
    },
    {
        "id": "SQ04", "category": "fraud_prevention",
        "question": "다음 중 피싱 문자의 특징이 아닌 것은?",
        "options": ["긴급한 어조 사용", "단축 URL 포함", "카드사 공식 앱에서 발송", "개인정보 입력 요구"],
        "correct": "카드사 공식 앱에서 발송",
        "explanation": "카드사 공식 앱의 알림은 안전합니다. 피싱 문자는 긴급성을 강조하고, 단축 URL로 유도하며, 개인정보를 요구합니다.",
    },
    {
        "id": "SQ05", "category": "saving",
        "question": "변동지출을 줄이는 가장 효과적인 방법은?",
        "options": ["모든 소비를 중단", "주 단위 예산 설정", "신용카드만 사용", "가계부 앱 삭제"],
        "correct": "주 단위 예산 설정",
        "explanation": "월 단위보다 주 단위로 예산을 나누면 관리가 쉽고, 초과 시 빠르게 인지할 수 있습니다.",
    },
    {
        "id": "SQ06", "category": "investing",
        "question": "사회 초년생이 가장 먼저 마련해야 할 재무 안전장치는?",
        "options": ["주식 투자", "비상금 (3~6개월 생활비)", "보험 가입", "부동산 투자"],
        "correct": "비상금 (3~6개월 생활비)",
        "explanation": "예상치 못한 실직, 질병 등에 대비하여 최소 3~6개월 생활비를 비상금으로 확보하는 것이 최우선입니다.",
    },
    {
        "id": "SQ07", "category": "budgeting",
        "question": "고정지출에 해당하지 않는 것은?",
        "options": ["월세", "통신비", "구독 서비스", "외식비"],
        "correct": "외식비",
        "explanation": "외식비는 매월 금액이 변동되는 변동지출입니다. 월세, 통신비, 구독료는 매월 일정한 고정지출입니다.",
    },
    {
        "id": "SQ08", "category": "fraud_prevention",
        "question": "온라인 결제 시 가장 안전한 방법은?",
        "options": ["실물 카드 번호 직접 입력", "가상 카드 번호 사용", "타인 카드 대리 결제", "공용 PC에서 결제"],
        "correct": "가상 카드 번호 사용",
        "explanation": "가상 카드 번호는 일회용으로 유출되어도 재사용할 수 없어 가장 안전합니다.",
    },
    {
        "id": "SQ09", "category": "saving",
        "question": "소비 전 '24시간 규칙'이란?",
        "options": ["24시간 안에 환불", "결제 후 24시간 대기", "구매 욕구 발생 후 24시간 대기 후 재판단", "하루에 한 번만 결제"],
        "correct": "구매 욕구 발생 후 24시간 대기 후 재판단",
        "explanation": "충동구매를 방지하기 위해 구매 욕구가 생기면 24시간 기다린 후 다시 생각해보는 방법입니다. 대부분 다음 날이면 구매 욕구가 사라집니다.",
    },
    {
        "id": "SQ10", "category": "investing",
        "question": "복리의 효과가 가장 큰 조건은?",
        "options": ["높은 수익률", "큰 원금", "긴 투자 기간", "빈번한 매매"],
        "correct": "긴 투자 기간",
        "explanation": "복리는 시간이 길수록 기하급수적으로 커집니다. 20대에 시작하면 같은 금액으로도 30대에 시작하는 것보다 훨씬 큰 자산을 만들 수 있습니다.",
    },
]


# ── 인메모리 저장소 ──────────────────────────────────────────

class EducationStore:
    """교육 프로그램 데이터 저장소."""

    def __init__(self) -> None:
        self._course_progress: dict[str, dict[str, CourseProgress]] = defaultdict(dict)  # user_id → course_id → progress
        self._challenge_enrollments: dict[str, dict[str, ChallengeEnrollment]] = defaultdict(dict)
        self._badges: dict[str, list[Badge]] = defaultdict(list)  # user_id → badges
        self._quiz_scores: dict[str, list[dict]] = defaultdict(list)  # user_id → [{quiz_type, score, date}]
        self._leaderboard_points: dict[str, int] = defaultdict(int)

    # ── 코스 진행 ──

    def start_course(self, user_id: str, course_id: str) -> CourseProgress:
        if course_id not in COURSES:
            raise ValueError(f"Course {course_id} not found")
        course = COURSES[course_id]
        progress = CourseProgress(
            user_id=user_id, course_id=course_id,
            current_step=1, total_steps=course.total_steps,
            completed=False, started_at=datetime.now(),
        )
        self._course_progress[user_id][course_id] = progress
        return progress

    def advance_course(self, user_id: str, course_id: str) -> CourseProgress:
        prog = self._course_progress.get(user_id, {}).get(course_id)
        if not prog:
            return self.start_course(user_id, course_id)
        if prog.current_step < prog.total_steps:
            prog.current_step += 1
        if prog.current_step >= prog.total_steps:
            prog.completed = True
            prog.completed_at = datetime.now()
            self._leaderboard_points[user_id] += 100
        return prog

    def get_course_progress(self, user_id: str, course_id: str) -> CourseProgress | None:
        return self._course_progress.get(user_id, {}).get(course_id)

    def get_all_progress(self, user_id: str) -> list[CourseProgress]:
        return list(self._course_progress.get(user_id, {}).values())

    # ── 챌린지 ──

    def enroll_challenge(self, user_id: str, challenge_id: str) -> ChallengeEnrollment:
        if challenge_id not in CHALLENGES:
            raise ValueError(f"Challenge {challenge_id} not found")
        ch = CHALLENGES[challenge_id]
        now = datetime.now()
        from datetime import timedelta
        enrollment = ChallengeEnrollment(
            user_id=user_id, challenge_id=challenge_id,
            status=ChallengeStatus.ACTIVE,
            start_date=now,
            end_date=now + timedelta(days=ch.duration_days),
            current_value=0, target_value=1.0, progress_pct=0,
        )
        self._challenge_enrollments[user_id][challenge_id] = enrollment
        return enrollment

    def update_challenge_progress(self, user_id: str, challenge_id: str, value: float) -> ChallengeEnrollment | None:
        enrollment = self._challenge_enrollments.get(user_id, {}).get(challenge_id)
        if not enrollment:
            return None
        enrollment.current_value = value
        enrollment.progress_pct = min(100.0, (value / enrollment.target_value) * 100) if enrollment.target_value > 0 else 0
        if enrollment.progress_pct >= 100:
            enrollment.status = ChallengeStatus.COMPLETED
            ch = CHALLENGES[challenge_id]
            self._award_badge(user_id, ch.badge_name, ch.badge_icon, f"{ch.name} 완료", challenge_id)
            self._leaderboard_points[user_id] += 200
        return enrollment

    def get_user_challenges(self, user_id: str) -> list[ChallengeEnrollment]:
        return list(self._challenge_enrollments.get(user_id, {}).values())

    # ── 배지 ──

    def _award_badge(self, user_id: str, badge_name: str, badge_icon: str, description: str, challenge_id: str) -> Badge:
        existing = [b for b in self._badges[user_id] if b.badge_name == badge_name]
        if existing:
            return existing[0]
        badge = Badge(
            badge_name=badge_name, badge_icon=badge_icon,
            description=description, earned_at=datetime.now(),
            challenge_id=challenge_id,
        )
        self._badges[user_id].append(badge)
        return badge

    def get_badges(self, user_id: str) -> list[Badge]:
        return self._badges.get(user_id, [])

    # ── 퀴즈 점수 ──

    def record_quiz_score(self, user_id: str, quiz_type: str, score: float, total: int, correct: int) -> None:
        self._quiz_scores[user_id].append({
            "quiz_type": quiz_type, "score": score,
            "total": total, "correct": correct,
            "date": datetime.now().isoformat(),
        })
        self._leaderboard_points[user_id] += int(score * 10)

    def get_quiz_history(self, user_id: str) -> list[dict]:
        return self._quiz_scores.get(user_id, [])

    # ── 리더보드 ──

    def get_leaderboard(self, top_n: int = 20) -> list[dict]:
        entries = []
        all_users = set(list(self._leaderboard_points.keys()) +
                        list(self._badges.keys()) +
                        list(self._challenge_enrollments.keys()))
        for uid in all_users:
            badges = self.get_badges(uid)
            challenges = [e for e in self.get_user_challenges(uid) if e.status == ChallengeStatus.COMPLETED]
            quiz_scores = self.get_quiz_history(uid)
            avg_score = sum(q["score"] for q in quiz_scores) / len(quiz_scores) if quiz_scores else 0
            entries.append({
                "user_id": uid,
                "badge_count": len(badges),
                "challenge_completed": len(challenges),
                "quiz_score_avg": round(avg_score, 1),
                "total_points": self._leaderboard_points.get(uid, 0),
            })
        entries.sort(key=lambda x: x["total_points"], reverse=True)
        for i, e in enumerate(entries[:top_n]):
            e["rank"] = i + 1
        return entries[:top_n]


# 싱글턴
education_store = EducationStore()
