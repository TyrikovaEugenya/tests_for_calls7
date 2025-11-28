
def detect_video_scenario(page) -> str:
    """
    Определяет сценарий:
    - "A": есть заставка-преролл (нельзя перемотать)
    - "B": можно сразу перематывать (прямой доступ к контенту)
    """
    try:
        # Сценарий A: есть оверлей преролла
        if page.locator(".preroll-overlay, .ad-overlay, [data-preroll]").is_visible(timeout=3000):
            return "A"
        # Сценарий B: есть seekbar сразу
        if page.locator(".plyr__progress__buffer").is_visible(timeout=3000):
            return "B"
    except:
        pass
    
    # Резерв: по тексту кнопки
    try:
        btn_text = page.locator(".plyr__controls button").inner_text().lower()
        if "пропустить" in btn_text or "skip" in btn_text:
            return "A"
        else:
            return "B"
    except:
        return "B"