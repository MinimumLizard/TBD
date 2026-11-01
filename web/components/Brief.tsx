// "At a glance": the few sentences a visitor needs before the detail, always visible (never collapsed). The lines
// are facts stated in plain words, built on the server from data the visitor is entitled to.
export default function Brief({ title, lines, when }: { title: string; lines: React.ReactNode[]; when?: React.ReactNode }) {
  if (lines.length === 0) return null;
  return (
    <section className="brief" aria-label={title}>
      <h2>{title}</h2>
      <ul>
        {lines.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
      {when && <p className="when">{when}</p>}
    </section>
  );
}
