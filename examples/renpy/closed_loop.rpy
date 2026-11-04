# adapted: explicit static jumps demonstrate a reachable closed loop.
label start:
    jump trapped

label trapped:
    "调查停在原地。"
    jump trapped

label reserved_ending:
    return
