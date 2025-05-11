from dataclasses import field, asdict, dataclass


@dataclass
class UISettings:
    @dataclass
    class Header:
        background_color: str = "#2196F3"
        color: str = "#FFFFFF"
        font_size: str = "1.8em"

    @dataclass
    class Sidebar:
        width: str = "280px"
        padding: str = "10px"
        background_color: str = "#F0F0F0"
        border_radius: str = "6px"
        gap: str = "8px"

    @dataclass
    class Labels:
        title_font_size: str = "1.3em"
        title_font_weight: str = "bold"
        subtitle_font_size: str = "1em"
        subtitle_font_weight: str = "500"
        info_font_size: str = "0.9em"
        info_color: str = "#666"
        margin_top: str = "8px"
        margin_bottom: str = "4px"

    @dataclass
    class ProgressBar:
        size: str = "sm"

    @dataclass
    class Separator:
        margin_top: str = "12px"
        margin_bottom: str = "8px"

    @dataclass
    class MainContent:
        font_size: str = "1.8em"
        font_weight: str = "600"
        subtitle_font_size: str = "1em"
        subtitle_color: str = "#444"
        margin_top: str = "16px"
        margin_bottom: str = "12px"

    header: Header = field(default_factory=Header)
    sidebar: Sidebar = field(default_factory=Sidebar)
    labels: Labels = field(default_factory=Labels)
    progress_bar: ProgressBar = field(default_factory=ProgressBar)
    separator: Separator = field(default_factory=Separator)
    main_content: MainContent = field(default_factory=MainContent)

    def __post_init__(self): ...


config = asdict(UISettings())
