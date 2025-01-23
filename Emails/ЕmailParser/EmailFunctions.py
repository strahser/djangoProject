

def clean(text):
    # clean text for creating a folder
    return "".join(c if c.isalnum() else "_" for c in text)