HIGH_TAGS = {'Interesting', 'Important', 'Trending'}


def calculate_importance(total_reactions, tags, links):
    score = 0

    if total_reactions >= 50:
        score += 3
    elif total_reactions >= 20:
        score += 2
    elif total_reactions >= 5:
        score += 1

    if any(t in HIGH_TAGS for t in tags):
        score += 2

    if any('github.com' in link for link in links):
        score += 1

    if score >= 5:
        return 4
    if score >= 3:
        return 3
    if score >= 1:
        return 2
    return 1
