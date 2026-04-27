import json
from docx import Document
import pandas as pd
import os
import math, random

def extract_info(doc_path):
    # 判断是doc还是docx
    conversation = []
    if doc_path.endswith(".docx"):
        doc = Document(doc_path)

        for para in doc.paragraphs:
            text = para.text.strip()
            single_turn = {}
            
            if text.startswith("客户:"):
                single_turn["input"] = text.split(":", 1)[1].strip()
            elif text.startswith("客户："):
                single_turn["input"] = text.split("：", 1)[1].strip()
            elif text.startswith("专员:"):
                single_turn["output"] = text.split(":", 1)[1].strip()
            elif text.startswith("专员："):
                single_turn["output"] = text.split("：", 1)[1].strip()

            if single_turn:
                conversation.append(single_turn)
        
        if not conversation:
            print(f"警告: 文件 {doc_path} 中没有提取到任何对话内容")
            return None

        if list(conversation[0].keys())[0] == 'output':
            conversation.insert(0, {'input': ''})
        if list(conversation[-1].keys())[0] == 'input':
            # conversation.append({'output': ''})
            conversation.pop()  # 删除最后一个元素，即客户说的话---需要保证是废话
    else:
        with open(doc_path, 'r', encoding='utf-8') as f:
            content = f.read()
    
        # 假设文本内容格式与之前相同（含"客户："、"专员："等标记）
        lines = [line.strip() for line in content.split('\n')  if line.strip()]
        # print(lines)
        
        for text in lines:
            single_turn = {}
            if text.startswith("客户:"):
                single_turn["input"] = text.split(":", 1)[1].strip()
            elif text.startswith("客户："):
                single_turn["input"] = text.split("：", 1)[1].strip()
            elif text.startswith("专员:"):
                single_turn["output"] = text.split(":", 1)[1].strip()
            elif text.startswith("专员："):
                single_turn["output"] = text.split("：", 1)[1].strip()
            if single_turn:
                conversation.append(single_turn)
        
        if not conversation:
            print(f"警告: 文件 {doc_path} 中没有提取到任何对话内容")
            return None

        if list(conversation[0].keys())[0] == 'output':
            conversation.insert(0, {'input': ''})
        if list(conversation[-1].keys())[0] == 'input':
            # conversation.append({'output': ''})
            conversation.pop()  # 删除最后一个元素，即客户说的话---需要保证是废话

    # print(conversation)

    # 检查对话顺序是否正确 
    for i in range(len(conversation)):
        current_keys = list(conversation[i].keys())
        if i % 2 == 0:  # 应该是input 
            if 'input' not in current_keys:
                print(f"警告: 文件 {doc_path} 对话顺序错误，期待input但未找到")
                return None 
        else:  # 应该是output 
            if 'output' not in current_keys:
                print(f"警告: 文件 {doc_path} 对话顺序错误，期待output但未找到")
                return None

    if len(conversation) % 2 != 0:
        print(f"警告: 文件 {doc_path} 对话轮次为奇数，添加空的output")
        return None
    
    dialogs = [{**conversation[idx], **conversation[idx+1]} for idx in range(0, len(conversation), 2)]

    return dialogs

def reformat_dialogs(dialogs):
    messages = []
    if "system" in dialogs[0]:
        messages.append({"role": "system", "content": dialogs[0]["system"]})
 
    # 处理所有对话轮次 
    for item in dialogs:
        if "input" in item:
            messages.append({"role": "user", "content": item["input"]})
        if "output" in item:
            messages.append({"role": "assistant", "content": item["output"]})
    
    result = {"messages": messages}
    return result


# def loss(message_data):
#     """
#     为output设计loss=False
#     随着对话轮次的增加，loss=True的概率逐渐增大
#     """
#     conversation_rounds = sum(1 for msg in message_data["messages"] if msg["role"] == "assistant")
    
#     transformed_messages = []
#     assistant_count = 0 
    
#     for msg in message_data["messages"]:
#         if msg["role"] != "assistant":
#             # 非assistant消息直接复制 
#             transformed_msg = msg.copy() 
#             transformed_messages.append(transformed_msg) 
#         else:
#             # assistant消息增加loss字段 
#             assistant_count += 1 
#             # 计算这一轮assistant的概率（越往后True概率越高）
#             # true_probability = 0.5 + 0.45 * (assistant_count / conversation_rounds)
#             true_probability = min(0.1 * math.exp(0.618 * (assistant_count - 1)), 0.9)
#             loss = str(random.random() < true_probability)
            
#             transformed_msg = msg.copy() 
#             transformed_msg["loss"] = loss 
#             transformed_messages.append(transformed_msg)
    
#     return {"messages": transformed_messages}


if __name__ == "__main__":
    # directory = "../simulation_data"
    directory = "./Yangqg_simulation_data"
    prompt_dir = "./cases_random"
    output_dir = "./dataset_sft"

    # excel_path = './simulation_case_id.xlsx'
    # df = pd.read_excel(excel_path)
    # simulation_to_case = {}
    # for index, row in df.iterrows(): 
    #     # simulation_name = row["序号"]  # 例如 "录音案例-1"
    #     # simulation_number = int(simulation_name.split("-")[1])   # 提取数字部分 
    #     simulation_number = row["序号"]
    #     case_id = row["客户序号"]
    #     # # 客户序号可能有两个，提取第一个编号
    #     # if type(case_id) == str:
    #     #     case_id = int(case_id.split("-")[0])
    #     simulation_to_case[simulation_number] = case_id

    multi_dialogs = []
    for filename in os.listdir(directory): 
        # if not filename.endswith(".docx"):
        #     print(filename)
        if filename.endswith(".docx") or filename.endswith(".doc"):
        # if filename.endswith("案例11.doc"):
            # print(filename)
            file_path = os.path.join(directory, filename)
            dialogs = extract_info(doc_path=file_path)

            if dialogs is None:
                print("Skip:" + filename)
                continue

            simulation_id = int(filename.split("案例")[1].split(".")[0])
            # case_id = simulation_to_case[simulation_id]
            case_id = simulation_id

            prompt_file = prompt_dir + "/case_" + str(case_id) + ".txt"
            with open(prompt_file, 'r', encoding='utf-8') as f: 
                prompt = f.read()
            f.close()
            
            dialogs[0]["system"] = "你是一个洋钱罐的催收专员，请根据客户的情况，使用合适的话术与客户进行沟通，争取让客户承诺还款。\n" + prompt

            # 调整顺序
            dialogs[0] = {key: dialogs[0][key] for key in ["system", "input", "output"]}

            # multi_dialogs.append({"conversation": dialogs})
            # Reformat
            messages = reformat_dialogs(dialogs)
            multi_dialogs.append(messages)
            # multi_dialogs.append(loss(messages))

    with open(output_dir + '/data_1111.json',  "wt", encoding="utf-8") as file:
        json.dump(multi_dialogs, file, ensure_ascii=False, indent=4)
        
