default has_clue = False
default alarmed = False
default reviewed = False

label start:
    menu:
        "搜索档案室":
            if alarmed:
                return
            else:
                menu:
                    "带走线索":
                        $ has_clue = True
                    "只做记录":
                        $ has_clue = False
                $ reviewed = True
        "直接撤离":
            jump leave
    if has_clue and reviewed:
        jump truth
    else:
        jump leave

label truth:
    "线索已确认。"
    return

label leave:
    if reviewed:
        "你完成了记录。"
        return
    else:
        jump empty

label empty:
    "你没有继续调查。"
    return
