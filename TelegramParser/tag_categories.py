TAG_CATEGORIES = {
    'Языки программирования': [
        'Python', 'GraphQL', 'Haskell', 'Go', 'TypeScript', 'Php', 'Cpp',
        'JavaScript', 'Rust', 'Perl', 'C', 'CSharp', 'Swift', 'Ruby',
        'Java', 'Dart', 'R', 'GDScript', 'ObjectiveC', 'SQL', 'RegEx',
    ],
    'Веб-разработка': [
        'Web', 'React', 'Node', 'CSS', 'JS', 'GTK', 'Interface', 'CMS', 'Browser',
    ],
    'Инфраструктура и DevOps': [
        'Docker', 'Deployment', 'SSH', 'Linux', 'Nix', 'MacOS', 'Windows',
        'Android', 'OS', 'Platform', 'VPN', 'Proxy', 'Emulation', 'deGoogle',
    ],
    'Данные и ML': [
        'Database', 'Data', 'Query', 'ORM', 'ML', 'Science',
    ],
    'Инструменты': [
        'Editor', 'Terminal', 'Manager', 'Generator', 'Downloader', 'Extension',
        'AdBlock', 'Analyzer', 'Compiler', 'Decompiler', 'Player', 'Messenger',
        'Notes', 'Helpdesk', 'Support', 'Code', 'File',
    ],
    'Автоматизация и боты': [
        'Automation', 'Bot', 'Telegram', 'Translation', 'Correction', 'Assistant',
    ],
    'Медиа и графика': [
        'Video', 'Graphics', '3D', 'Rendering', 'Icons', 'Visualization',
    ],
    'Безопасность и приватность': [
        'Privacy', 'Blockchain', 'Cryptocurrency',
    ],
    'Операционные системы': [
        'Linux', 'MacOS', 'Windows', 'Android', 'OS', 'Nix', 'deGoogle',
    ],
}

ALL_TAGS = [
    'Interesting', 'Archive', 'Python', 'GraphQL', 'Database', 'Haskell',
    'File', 'Go', 'Shell', 'Web', 'React', 'TypeScript', 'Automation',
    'Deployment', 'Php', 'Game', 'Cpp', 'Client', 'JavaScript', 'Rust',
    'Manager', 'Windows', 'Monitoring', 'C', 'Perl', 'Browser', 'Privacy',
    'Editor', 'Code', 'Data', 'Query', 'Terminal', 'Google', 'Blockchain',
    'Docker', 'CSharp', 'SSH', 'Emulation', 'Rendering', 'Nix', 'Video',
    'Graphics', 'JS', 'GTK', 'Visualization', '3D', 'Proxy', 'Notion',
    'Flutter', 'Bot', 'Telegram', 'CMS', 'Node', 'Generator', 'Swift',
    'Platform', 'Linux', 'Assistant', 'Dart', 'MC', 'Decompiler', 'VPN',
    'Correction', 'Icons', 'CSS', 'Mail', 'Ruby', 'Cryptocurrency', 'ML',
    'Testing', 'MacOS', 'ObjectiveC', 'Engine', 'Useful', 'Translation',
    'Player', 'Messenger', 'Java', 'Downloader', 'Extension', 'OS',
    'AdBlock', 'Analyzer', 'Science', 'R', 'ORM', 'Async', 'Android',
    'RegEx', 'SQL', 'GDScript', 'deGoogle', 'Notes', 'Helpdesk', 'Support',
    'Interface',
]


def get_category_for_tag(tag_name):
    for category_name, tags in TAG_CATEGORIES.items():
        if tag_name in tags:
            return category_name
    return 'Прочее'


def get_all_categories():
    return list(TAG_CATEGORIES.keys()) + ['Прочее']
