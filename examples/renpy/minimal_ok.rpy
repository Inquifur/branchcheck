default has_photo = False

label start:
    menu:
        "调查实验室":
            $ has_photo = True
        "暂时离开":
            jump leave
    if has_photo:
        jump truth
    else:
        jump leave

label truth:
    "你确认了照片中的线索。"
    return

label leave:
    "调查暂告一段落。"
    return
