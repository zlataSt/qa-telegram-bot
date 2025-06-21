import google.generativeai as genai
from config import GEMINI_API_KEY
from prompts import MANUAL_TESTS_PROMPT_TEMPLATE, AUTOTEST_PROMPT_TEMPLATE

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("models/gemini-1.5-flash-latest")

def generate_test_cases(feature_description: str) -> str:
    """Генерирует мануальные тест-кейсы."""
    prompt = MANUAL_TESTS_PROMPT_TEMPLATE.format(feature_description=feature_description)
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error in generate_test_cases: {e}")
        return "Не удалось сгенерировать ответ. Попробуйте снова."

def generate_autotest_code(manual_test_text: str, language: str) -> str:
    """Генерирует код автотеста на основе мануального теста."""
    prompt = AUTOTEST_PROMPT_TEMPLATE.format(manual_test_text=manual_test_text, language=language)
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error in generate_autotest_code: {e}")
        return f"// Ошибка при генерации кода: {e}"