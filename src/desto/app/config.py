from dataclasses import asdict, dataclass, field


@dataclass
class UISettings:
    @dataclass
    class Header:
        background_color: str = "#2196F3"
        color: str = "#FFFFFF"
        font_size: str = "1.8em"

    @dataclass
    class Sidebar:
        width: str = "180px"  # was 280px
        padding: str = "4px"  # was 10px
        background_color: str = "#F0F0F0"
        border_radius: str = "6px"
        gap: str = "8px"

    @dataclass
    class Labels:
        title_font_size: str = "1.7em"
        title_font_weight: str = "bold"
        subtitle_font_size: str = "1.5em"
        subtitle_font_weight: str = "500"
        info_font_size: str = "1.1em"
        info_color: str = "#666"
        margin_top: str = "8px"
        margin_bottom: str = "4px"

    @dataclass
    class ProgressBar:
        size: str = "sm"

    @dataclass
    class CPUCores:
        max_columns: int = 4  # Number of columns to display cores in
        show_percentage: bool = True
        bar_height: str = "6px"
        core_label_size: str = "0.9em"

    @dataclass
    class Separator:
        margin_top: str = "12px"
        margin_bottom: str = "8px"

    @dataclass
    class ScriptSettings:
        supported_extensions: list = field(default_factory=lambda: [".sh", ".py"])
        default_script_type: str = "bash"
        python_executable: str = "python3"
        show_script_type_icons: bool = True

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
    cpu_cores: CPUCores = field(default_factory=CPUCores)
    separator: Separator = field(default_factory=Separator)
    script_settings: ScriptSettings = field(default_factory=ScriptSettings)
    main_content: MainContent = field(default_factory=MainContent)

    def __post_init__(self): ...


config = asdict(UISettings())
