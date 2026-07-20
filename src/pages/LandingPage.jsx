import './LandingPage.css'
import heroImage from '../assets/landing-hero.png'

const FIRM_NAME = 'Alder & Stone'

const PRACTICES = [
  {
    number: '01',
    title: 'Business & Contracts',
    copy: 'Clear-eyed counsel for agreements, negotiations, and the decisions that shape what comes next.',
  },
  {
    number: '02',
    title: 'Family Law',
    copy: 'Steady, discreet guidance through matters that require both legal precision and human judgment.',
  },
  {
    number: '03',
    title: 'Estate Planning',
    copy: 'Thoughtful plans that protect your wishes, your family, and the legacy you intend to leave.',
  },
]

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  )
}

export default function LandingPage() {
  return (
    <main className="landing-page">
      <header className="landing-nav">
        <a className="landing-brand" href="#top" aria-label={`${FIRM_NAME} home`}>
          <span className="landing-monogram">A<span>S</span></span>
          <span className="landing-brand-copy">
            <strong>{FIRM_NAME}</strong>
            <small>Attorneys at Law</small>
          </span>
        </a>

        <nav className="landing-links" aria-label="Main navigation">
          <a href="#practice">Practice areas</a>
          <a href="#approach">Our approach</a>
          <a href="#contact">Contact</a>
        </nav>

        <div className="landing-nav-actions">
          <a className="landing-staff-link" href="#login">Staff portal</a>
          <a className="landing-nav-cta" href="#intake">Start your intake</a>
        </div>
      </header>

      <section className="landing-hero" id="top">
        <div className="landing-hero-copy">
          <p className="landing-eyebrow"><span /> Counsel for consequential moments</p>
          <h1>Clarity when the path forward matters most.</h1>
          <p className="landing-hero-lede">
            Practical legal counsel, grounded in preparation and delivered with the attention your matter deserves.
          </p>

          <div className="landing-hero-actions">
            <a className="landing-primary-cta" href="#intake">
              Tell us about your matter <ArrowIcon />
            </a>
            <a className="landing-text-link" href="#practice">Explore our practice <span>↓</span></a>
          </div>

          <div className="landing-confidence">
            <div className="landing-confidence-mark">✓</div>
            <p><strong>Confidential from the first step.</strong><br />Secure intake. Thoughtful review. Prompt response.</p>
          </div>
        </div>

        <div className="landing-hero-visual">
          <img src={heroImage} alt="Sunlit columns in a distinguished courthouse corridor" />
          <div className="landing-image-caption">
            <span>Serving clients with conviction</span>
            <span>Est. 1998 · Your City</span>
          </div>
        </div>
      </section>

      <section className="landing-proof" aria-label="Firm highlights">
        <p>Trusted counsel. Measured action.</p>
        <div><strong>25+</strong><span>Years of combined experience</span></div>
        <div><strong>01</strong><span>Dedicated team, start to finish</span></div>
        <div><strong>24h</strong><span>Typical response to new inquiries</span></div>
      </section>

      <section className="landing-practice" id="practice">
        <div className="landing-section-intro">
          <p className="landing-kicker">How we can help</p>
          <h2>Focused counsel.<br /><em>Lasting outcomes.</em></h2>
          <p>We pair rigorous legal work with direct, useful advice—so you understand not only your options, but what each one means.</p>
        </div>

        <div className="landing-practice-list">
          {PRACTICES.map((practice) => (
            <article className="landing-practice-card" key={practice.number}>
              <span>{practice.number}</span>
              <div>
                <h3>{practice.title}</h3>
                <p>{practice.copy}</p>
              </div>
              <a href="#intake" aria-label={`Ask about ${practice.title}`}><ArrowIcon /></a>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-approach" id="approach">
        <div className="landing-approach-panel">
          <p className="landing-kicker">Our standard</p>
          <blockquote>“You should never have to wonder where your matter stands.”</blockquote>
          <p className="landing-approach-copy">
            We built our process around communication: clear expectations, candid recommendations, and updates at every meaningful turn.
          </p>
          <div className="landing-signature">Alder & Stone <span>— Founding Partners</span></div>
        </div>

        <div className="landing-steps">
          <p className="landing-kicker">What happens next</p>
          <ol>
            <li><span>1</span><div><strong>Share your situation</strong><p>Complete a secure, five-minute intake.</p></div></li>
            <li><span>2</span><div><strong>We review the details</strong><p>Our team checks fit and potential conflicts.</p></div></li>
            <li><span>3</span><div><strong>Speak with counsel</strong><p>If we can help, we’ll arrange a focused consultation.</p></div></li>
          </ol>
        </div>
      </section>

      <section className="landing-closing" id="contact">
        <p className="landing-kicker">Begin with confidence</p>
        <h2>Your next step can be a clear one.</h2>
        <p>Tell us what brings you here. Your information is confidential and submitting an inquiry takes only a few minutes.</p>
        <a className="landing-primary-cta landing-closing-cta" href="#intake">
          Start a confidential intake <ArrowIcon />
        </a>
      </section>

      <footer className="landing-footer">
        <div className="landing-brand landing-footer-brand">
          <span className="landing-monogram">A<span>S</span></span>
          <span className="landing-brand-copy"><strong>{FIRM_NAME}</strong><small>Attorneys at Law</small></span>
        </div>
        <p>Demo firm identity · Replace with buyer branding</p>
        <div><a href="#login">Staff portal</a><span>© 2026 {FIRM_NAME}</span></div>
      </footer>
    </main>
  )
}
