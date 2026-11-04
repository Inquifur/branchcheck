default first = True
default second = True
default result_first = False
default result_second = False

label start:
    if first:
        $ result_first = True
    elif second:
        $ result_second = True
    else:
        pass
    return
