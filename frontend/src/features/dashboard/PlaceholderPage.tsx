interface PlaceholderPageProps {
  title: string;
  description: string;
  stage: string;
}

export function PlaceholderPage({ title, description, stage }: PlaceholderPageProps) {
  return (
    <section className="placeholder-page" aria-labelledby="placeholder-title">
      <p className="section-kicker">Route ready · {stage}</p>
      <h2 id="placeholder-title">{title}</h2>
      <p>{description}</p>
      <div className="placeholder-page__line" aria-hidden="true" />
      <small>当前阶段只建立可导航入口，业务界面将在对应阶段实现。</small>
    </section>
  );
}
