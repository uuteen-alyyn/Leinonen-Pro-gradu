import json
import pandas as pd

# Define the master question list for ordering and labeling
QUESTIONS = [
    ("A1", "Does the article suggest that some level of government has the ability to alleviate the problem?"),
    ("A2", "Does the article suggest that some level of the government is responsible for the problem?"),
    ("A3", "Does the article suggest solution(s) to the problem?"),
    ("A4", "Does the article make references to moral, religious or philosophical tenets?"),
    ("A5", "Does the article frame actions as good and / or evil, or compare the acceptability of the actions of different actors to one another?"),
    ("A6", "Does the article offer specific social prescriptions about how to behave?"),
    ("A7", "Does the article spesifically reference European, Western, Chinese, Confucian, Russian or any other types of traditional / civilizational value systems?"),
    ("A8", "Does the article portray Russia as a pro-active actor changing the world?"),
    ("A9", "Does the article portray Russia as a reactive actor trying to cope with the changing world?"),
    ("A10", "Does regional (multilateral) cooperation or the international community play a major in solving the central problem of the article?"),
    ("B1", "Does the story reflect disagreement between parties-individuals-groups-countries?"),
    ("B2", "Does the story refer to two sides or to more than two sides of the problem or issue?"),
    ("B3", "Does the conflict involve, affect or even threaten vital national interests of a conflict party?"),
    ("B4", "Is there a mention of financial losses or gains now or in the future?"),
    ("B5", "Is there a reference to economic consequences of pursuing or not pursuing a course of action?"),
    ("B6", "Does the article talk about a win-win situation or a shared economic benefit for both parties?"),
    ("B7", "Does the article set the welfare of humans, citizens or communities as a major goal for action?"),
    ("B8", "Does the article reference the questions of armscontrol, detente or peace mediation?"),
    ("B9", "Does the article talk about climate change or ecological issues as a central problem?"),
    ("B10", "Does the article talk about eradicating poverty, increasing education or other sustainable development as a central problem?"),
]

def parse_jsonl_data(filename):
    data = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                entry = json.loads(line)
                article_id = entry.get("custom_id")
                if article_id:
                    data[article_id] = {
                        "answers": entry.get("answers", {}),
                        "commentary": entry.get("justification", "")
                    }
    except FileNotFoundError:
        print(f"Warning: {filename} not found.")
    return data

# 1. Load data
gemini_data = parse_jsonl_data('gemini_results.jsonl')
claude_data = parse_jsonl_data('out_claude.jsonl')
openai_data = parse_jsonl_data('out_openai.jsonl')

all_ids = sorted(set(list(gemini_data.keys()) + list(claude_data.keys()) + list(openai_data.keys())))

# 2. Process into Excel
with pd.ExcelWriter('AI_Comparison_Formatted.xlsx', engine='xlsxwriter') as writer:
    workbook = writer.book
    wrap_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
    header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
    justification_header_format = workbook.add_format({'bold': True, 'italic': True, 'bg_color': '#EAEAEA'})

    for art_id in all_ids:
        rows = []
        
        # Build the question rows
        for code, question_text in QUESTIONS:
            full_header = f"{code}: {question_text}"
            rows.append({
                "Question / Justification": full_header,
                "Gemini": gemini_data.get(art_id, {}).get("answers", {}).get(code, "N/A"),
                "Claude": claude_data.get(art_id, {}).get("answers", {}).get(code, "N/A"),
                "ChatGPT": openai_data.get(art_id, {}).get("answers", {}).get(code, "N/A")
            })

        # Add the Justification row at the bottom
        rows.append({
            "Question / Justification": "FULL JUSTIFICATION / COMMENTARY",
            "Gemini": gemini_data.get(art_id, {}).get("commentary", ""),
            "Claude": claude_data.get(art_id, {}).get("commentary", ""),
            "ChatGPT": openai_data.get(art_id, {}).get("commentary", "")
        })

        df = pd.DataFrame(rows)
        sheet_name = art_id[:31]
        df.to_excel(writer, sheet_name=sheet_name, index=False)

        # Formatting
        worksheet = writer.sheets[sheet_name]
        worksheet.set_column('A:A', 60, wrap_format)  # Question column
        worksheet.set_column('B:D', 40, wrap_format)  # Model columns
        
        # Apply special formatting to the last row (Commentary)
        last_row_idx = len(rows)
        worksheet.set_row(last_row_idx, 300, wrap_format) 

print("Done! 'AI_Comparison_Formatted.xlsx' has been created.")