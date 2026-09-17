/** ICP 备案页脚（合规要求）：全站底部居中展示，链接至工信部备案官网。
 * 备案号默认读取 VITE_ICP_NUMBER（构建期注入），缺省用内置值；置空字符串则不展示。
 */
const ICP_NUMBER: string = import.meta.env.VITE_ICP_NUMBER ?? "蜀ICP备2026054348号";
const GA_NUMBER: string = import.meta.env.VITE_GA_NUMBER ?? '川公网安备51015602002236号'

export function IcpFooter() {
  if (!ICP_NUMBER) return null;
  return (
    <footer className="pointer-events-none fixed inset-x-0 bottom-1 z-10 text-center">
      <a
        href="https://beian.miit.gov.cn/"
        target="_blank"
        rel="noreferrer"
        className="pointer-events-auto text-[11px] text-slate-500 transition-colors hover:text-brand-light"
      >
        {ICP_NUMBER}
      </a>
      <span
        className="pointer-events-auto text-[11px] text-slate-500 transition-colors hover:text-brand-light ml-5"
      >
        {GA_NUMBER}
      </span>
    
    </footer>
  );
}
