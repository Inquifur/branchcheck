default has_access = False
default continued = False

label start:
    menu:
        "进入密室" if has_access:
            $ continued = False
    $ continued = True
    return
