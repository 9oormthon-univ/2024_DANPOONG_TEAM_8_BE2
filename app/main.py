from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel
from query.get_character_type_by_id import get_character_type_by_user, get_character_info
from function.chat_bot import custom_chatbot
from query.get_userid_by_kakao import get_userID
from fastapi.middleware.cors import CORSMiddleware  # CORS 미들웨어 import
from function.buddy_comment import create_feedback
from query.get_mission_content import get_mission_content_and_feedback
from query.get_check_lists_by_id import fetch_check_lists
from query.get_area_type_by_area_id import get_area_type_by_area_id
from function.analysis import generate_analysis_response
from query.post_mission_to_db import insert_mission_to_db
from function.create_missions import create_missions
from .Questions import ALL_QUESTIONS

app = FastAPI()

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://localhost:5173",
        "https://buddy-lovat.vercel.app/"
                   
        ],  # 모든 오리진 허용, 필요시 특정 도메인으로 제한 가능
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# 요청 모델 정의
class QuestionRequest(BaseModel):
    question: str



@app.post("/api/ask", tags=['AI_ask'], description="사용자와 소통할 수 있는 맞춤형 감성 챗봇입니다. 선택한 캐릭터에 따라 대답하는 아이가 라집니다.")
async def ask_question(request: QuestionRequest, kakao_id: str = Header(...)):
    try:
        # 카카오 ID로 character_type 조회
        character_type = await get_character_type_by_user(kakao_id)
         # 함수 호출 시 character_type 전달

        if not character_type:
            raise HTTPException(status_code=404, detail="Character type not found for the user.")
        
        print("request입니다" , request)
        print("캐릭터타입니다", character_type)
        answer = custom_chatbot(request.question, character_type[0])
        return {"answer": answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/generate-missions/", tags=["AI_mission_generate & Custom_analysis"], 
        description="Kakao ID를 기반으로 사용자 맞춤형 분석을 진행하고 미션을 DB에 저장하는 API입니다.", 
        )
async def generate_missions(
    kakao_id: str = Header(..., description= "카카오 사용자 ID"),
    check_list_id: int = Query(..., description= "사용자 설문 ID"),

):
    """
    Kakao ID를 헤더에서 받아 사용자 맞춤형 미션을 생성합니다.
    """
    # Kakao ID를 이용해 member_id 조회
    member_id = await get_userID(kakao_id)

    
    if not member_id:
        raise HTTPException(status_code=404, detail="해당 Kakao ID에 대한 사용자 정보를 찾을 수 없습니다.")
    
    # 사용자 ID 기반 데이터베이스 조회
    print("체크리스트 아이디 :", check_list_id)

    db_result = await fetch_check_lists(check_list_id)
    print("DB_RESULT\n", db_result)
    print("DB_AREA\n", db_result[0]['area'])

    area_type = await get_area_type_by_area_id(db_result[0]['area'])
    print("Main에서 받는 area_type:\n",area_type)
    report = generate_analysis_response(db_result, area_type) #여기서 사용자 분석을 합니다잉


    print("Report 결과입니다 : \n", report)
    if not db_result or "error" in db_result:
        raise HTTPException(status_code=500, detail="데이터베이스 조회 중 오류 발생")

    # 각 행에 대해 미션 생성
    all_missions = []
    
    for row in db_result:
        db_ques = row["questions"]
        weights = [
            db_ques["firstQ"],
            db_ques["secondQ"],
            db_ques["thirdQ"],
            db_ques["fourthQ"],
            db_ques["fifthQ"],
            db_ques["sixthQ"],
            db_ques["seventhQ"],
            db_ques["eighthQ"],
        ]
        if area_type == 'DAILY_LIFE' :
            QUESTIONS = ALL_QUESTIONS["DAILY_LIFE"]
            file_path = 'files/Daily_Life.txt'
            
        elif area_type == 'MONEY_MANAGEMENT' :
            QUESTIONS = ALL_QUESTIONS["MONEY_MANAGEMENT"]
            file_path = 'files/Money_Management.txt'

        elif area_type == 'SELF_MANAGEMENT' :
            QUESTIONS = ALL_QUESTIONS["SELF_MANAGEMENT"]
            file_path = 'files/SELF_MANAGEMENT.txt'

        elif area_type == 'SOCIETY' :
            QUESTIONS = ALL_QUESTIONS["SOCIETY"]
            file_path = 'files/SOCIETY.txt'

        missions = create_missions(QUESTIONS, weights, file_path)

        # "id", "area", "member" 값을 row에서 추출
        all_missions.append({
            "id": row["id"], 
            "area_id": row["area"], 
            "member": row["member"],  # row["member_id"] → row["member"]로 수정
            "missions_list": missions
        })
    print("ALL_MISSIONS: ",all_missions)
    # 미션 데이터를 DB에 삽입
    await insert_mission_to_db(all_missions[0])

    return {"report": report}



@app.post("/api/buddy-feedback", tags=['Buddy_Feedback'], 
          description="사용자가 미션에 대한 버디 피드백을 제공하는 API입니다.")
async def provide_buddy_feedback(
    kakao_id: str = Header(..., description="카카오 사용자 ID", alias="kakao-id"),  # Header의 경우 하이픈 사용
    mission_id: int = Query(..., description="피드백을 제공할 미션의 ID"),  # mission_id는 1 이상의 정수
):
    try:
        # 나머지 코드는 동일
        member_id = await get_userID(kakao_id)
        print(member_id)
        print(mission_id)
        if not member_id:
            raise HTTPException(status_code=404, detail="Kakao ID not found.")
            
        level, char_type = await get_character_info(member_id)
        print(level, char_type, "레벨과 캐릭터타입 \n")
        content, feedback = await get_mission_content_and_feedback(member_id, mission_id)
        
        feedback_result = create_feedback(content, feedback, char_type)
        
        return {
            "status": "success",
            "message": "Feedback submitted successfully.",
            "buddy_feedback": feedback_result,
            "char_type": char_type,
            "character_level": level,
            "user_mission" : content,
            "user_feedback" : feedback
        }

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        print(f"Error in provide_buddy_feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))