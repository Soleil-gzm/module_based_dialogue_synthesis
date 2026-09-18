# config.py

CONFIG = {
    "suning_backend": {
        "name": "苏宁后端",
        "enabled": False,             # 是否启用该业务线
        "seed": 39,
        "total_cases": 60000,
        "combinations_path": "combinations-suning-backend-6w.json",
        "system_dir": "my_case/suning-backend/system",
        "replace_dir": "my_case/suning-backend/replace",
        "prompt_system_path": "generate_task/prompt/case_gr_Suning-backend/prompt_template_for_system.txt",
        "prompt_replace_path": "generate_task/prompt/case_gr_Suning-backend/prompt_template_for_backbone_replace.txt",
    },
    "s1": {
        "name": "S1首催",
        "enabled": True,
        "seed": 39,
        "total_cases": 60000,
        "combinations_path": "combinations-S1-6w.json",
        "system_dir": "case_generate/S1/systemS1-6w",
        "replace_dir": "case_generate/S1/replaceS1-6w",
        "prompt_system_path": "scripts_general/case_generator/prompt/S1_due/prompt_template_for_system-S1-new.txt",
        "prompt_replace_path": "scripts_general/case_generator/prompt/prompt_template_for_backbone_replace.txt",
    },
    "s1_follow": {
        "name": "S1跟催",
        "enabled": True,
        "seed": 35,
        "total_cases": 20000,
        "combinations_path": "combinations-S1-follow-2w.json",
        "system_dir": "case_generate/M0/systemS1-follow-2w",
        "replace_dir": "case_generate/M0/replaceS1-follow-2w",
        "prompt_system_path": "scripts_general/case_generator/prompt/S1_due/prompt_template_for_system-S1-new-follow.txt",
        "prompt_replace_path": "scripts_general/case_generator/prompt/prompt_template_for_backbone_replace.txt",
    },
    "m0": {
        "name": "M0未逾期",
        "enabled": True,
        "seed": 45,
        "total_cases": 40000,
        "combinations_path": "combinations-M0-4w.json",
        "system_dir": "case_generate/M0/systemM0_4w",
        "replace_dir": "case_generate/M0/replaceM0_4w",
        "prompt_system_path": "scripts_general/case_generator/prompt/M0_notdue/prompt_template_for_system-M0-new-0917.txt",
        "prompt_replace_path": "scripts_general/case_generator/prompt/prompt_template_for_backbone_replace.txt",
    },
    "m0_follow": {
        "name": "M0跟催",
        "enabled": True,
        "seed": 45,
        "total_cases": 10000,
        "combinations_path": "combinations-M0-follow-1w.json",
        "system_dir": "case_generate/M0/systemM0-follow-1w",
        "replace_dir": "case_generate/M0/replaceM0-follow-1w",
        "prompt_system_path": "scripts_general/case_generator/prompt/M0_notdue/prompt_template_for_system-M0-new-follow-0917.txt",
        "prompt_replace_path": "scripts_general/case_generator/prompt/prompt_template_for_backbone_replace.txt",
    }
}