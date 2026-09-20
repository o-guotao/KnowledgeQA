import { SECTIONS } from "../showcaseMath";

/** 顶部三栏：logo 左 / 五节导航中 / 署名右。落点由 sectionTarget 现算（见 ShowcasePage）。 */
interface TopbarProps {
  /** 当前节下标（0 起，与 SECTIONS 对应） */
  sectionIndex: number;
  onGoToSection: (i: number) => void;
}

export function Topbar({ sectionIndex, onGoToSection }: TopbarProps) {
  return (
    <header className="topbar">
      <span className="topbar__logo">KQA</span>
      <nav className="topbar__nav" aria-label="分节导航">
        {SECTIONS.map((s, i) => (
          <button
            key={s.en}
            type="button"
            className={`topbar__tab${i === sectionIndex ? " is-active" : ""}`}
            onClick={() => onGoToSection(i)}
          >
            {s.zh}
          </button>
        ))}
      </nav>
      <span className="topbar__tagline">
        AGENT DESIGNER
        <em>From chatbots to doers.</em>
      </span>
    </header>
  );
}
