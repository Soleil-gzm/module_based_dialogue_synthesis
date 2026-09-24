# config.py
# 同一个模块若有多套 case 配置，写成 list 即可，
# run.py 会依次遍历执行；只有一套时写 dict 也兼容。

CONFIG = {
    "m3_plus": [
        {
            "name": "M3plus_首催_协商还款",
            "enabled": True,
            "seed": 113,
            "total_cases": 40000,
            "combinations_path": "datas/backbone_data_suning-backend/case/combinations/combinations-M3plus-协商还款-4w.json",
            "system_dir": "datas/backbone_data_suning-backend/case/case_DS/systemM3plus_DS_4w",
            "replace_dir": "datas/backbone_data_suning-backend/case/case_DS/replaceM3plus_DS_4w",
            "prompt_system_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_system_首催_协商还款.txt",
            "prompt_replace_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_backbone_replace.txt",
            "testify": {
                "system_dir": "datas/backbone_data_suning-backend/case/testify_case/system",
                "replace_dir": "datas/backbone_data_suning-backend/case/testify_case/replace",
                "start": 100,
                "end": 199,
                "seed": 10113,
            },
        },
        {
            "name": "M3plus首催_法言法语",
            "enabled": True,
            "seed": 115,
            "total_cases": 40000,
            "combinations_path": "datas/backbone_data_suning-backend/case/combinations/combinations-M3plus-法言法语-4w.json",
            "system_dir": "datas/backbone_data_suning-backend/case/case_L/systemM3plus_L_4w",
            "replace_dir": "datas/backbone_data_suning-backend/case/case_L/replaceM3plus_L_4w",
            "prompt_system_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_system_首催_法言法语.txt",
            "prompt_replace_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_backbone_replace.txt",
            "testify": {
                "system_dir": "datas/backbone_data_suning-backend/case/testify_case/system",
                "replace_dir": "datas/backbone_data_suning-backend/case/testify_case/replace",
                "start": 300,
                "end": 399,
                "seed": 10115,
            },
        }
    ]
    # "m3_plus_follow":[
    #     {
    #         "name": "M3plus_跟催_协商还款",
    #         "enabled": True,
    #         "seed": 112,
    #         "total_cases": 20000,
    #         "combinations_path": "datas/backbone_data_suning-backend/case/combinations/combinations-M3plus-follow-协商还款-2w.json",
    #         "system_dir": "datas/backbone_data_suning-backend/case/case_DS/systemM3plus_follow_DS_2w",
    #         "replace_dir": "datas/backbone_data_suning-backend/case/case_DS/replaceM3plus_follow_DS_2w",
    #         "prompt_system_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_system_跟催_协商还款.txt",
    #         "prompt_replace_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_backbone_replace.txt",
    #         "testify": {
    #             "system_dir": "datas/backbone_data_suning-backend/case/testify_case/system",
    #             "replace_dir": "datas/suning_backend_0924/case/testify_case/replace",
    #             "start": 0,
    #             "end": 99,
    #             "seed": 10112,
    #         },
    #     },
    #     {
    #         "name": "M3plus跟催_法言法语",
    #         "enabled": True,
    #         "seed": 114,
    #         "total_cases": 20000,
    #         "combinations_path": "datas/backbone_data_suning-backend/case/combinations/combinations-M3plus-follow-法言法语-2w.json",
    #         "system_dir": "datas/backbone_data_suning-backend/case/case_L/systemM3plus_follow_L_2w",
    #         "replace_dir": "datas/backbone_data_suning-backend/case/case_L/replaceM3plus_follow_L_2w",
    #         "prompt_system_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_system_跟催_法言法语.txt",
    #         "prompt_replace_path": "datas/backbone_data_suning-backend/case_gr_Suning-backend/prompt_template_for_backbone_replace.txt",
    #         "testify": {
    #             "system_dir": "datas/backbone_data_suning-backend/case/testify_case/system",
    #             "replace_dir": "datas/backbone_data_suning-backend/case/testify_case/replace",
    #             "start": 200,
    #             "end": 299,
    #             "seed": 10114,
    #         },
    #     }
    # ]
}
