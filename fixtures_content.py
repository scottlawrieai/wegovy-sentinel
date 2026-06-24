"""
Canned fixtures for content_audit.py --test / --seed.

These are compact, representative copies of the live top-5 "wegovy pill" pages
(June 2026), grounded in their real titles and on-page content. They let the
audit logic and the dashboard be exercised offline (the GitHub Action runner
fetches the real pages live; this session's egress policy cannot).
"""

# phrase_organic CSV (Domain;Url), rank = row order. SOP is absent from the
# top-6 on purpose, so build_audit() appends our own page for comparison.
FIXTURE_SERP = (
    "Domain;Url\n"
    "www.wegovy.com;https://www.wegovy.com/obesity/is-wegovy-right-for-me/wegovy-pill-results.html\n"
    "onlinedoctor.superdrug.com;https://onlinedoctor.superdrug.com/wegovy-pill.html\n"
    "www.joinvoy.com;https://www.joinvoy.com/weight-loss/medications/wegovy-pill\n"
    "www.pharmica.co.uk;https://www.pharmica.co.uk/weight-loss/wegovy-oral-tablet/\n"
    "www.wegovy.com;https://www.wegovy.com/\n"
    "onlinedoctor.boots.com;https://onlinedoctor.boots.com/treatments/wegovy\n"
)


def _page(title, desc, h1, body, faqs_html="", ld=""):
    faq_ld = f'<script type="application/ld+json">{ld}</script>' if ld else ""
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
{faq_ld}
</head><body>
<nav>Home Weight loss Treatments Account Basket</nav>
<header>Site header — sign in — free delivery</header>
<main>
<h1>{h1}</h1>
{body}
{faqs_html}
</main>
<footer>Registered pharmacy. GPhC 0000000. Terms. Privacy.
<script>console.log('analytics noise that must be ignored')</script></footer>
</body></html>"""


SOP = _page(
    title="Buy Wegovy Pill Online UK | Oral Semaglutide",
    desc="Buy the Wegovy pill (oral semaglutide) online in the UK. The same active "
         "ingredient as the injection, taken as a daily tablet. Start your assessment.",
    h1="Buy the Wegovy Pill Online (Oral Semaglutide)",
    body="""
<p>The Wegovy pill contains the same active ingredient as the injection,
semaglutide, taken as a daily tablet with no needles. It helps you feel full
sooner and makes it easier to eat less. A special coating protects the medicine
in your stomach so your body can absorb it.</p>
<h2>How the Wegovy pill works</h2>
<p>Oral Wegovy is a GLP-1 medicine. It works on appetite so you feel fuller for
longer. The tablet must be taken once daily on an empty stomach, swallowed with
a little plain water, then wait 30 minutes before food.</p>
<h2>Wegovy pill dosing</h2>
<p>Treatment starts low and increases over time, up to a 25mg daily maintenance
dose. The dosing schedule steps up gradually to reduce side effects.</p>
<h2>Wegovy pill results</h2>
<p>In the OASIS 4 clinical trial the Wegovy pill produced around 16% average
weight loss over 64 weeks, close to the Wegovy injection.</p>
<h2>Wegovy pill vs injection</h2>
<p>The pill is a daily tablet; the injection is weekly. Both contain semaglutide.</p>
<h2>Wegovy pill price in the UK</h2>
<p>The Wegovy pill is available in the UK following MHRA approval. Pricing is
comparable to the injection; NHS access is unlikely before 2027.</p>
""",
    faqs_html="""
<section><h2>Wegovy pill FAQs</h2>
<details><summary>How does the Wegovy pill work?</summary><p>It is oral semaglutide, a GLP-1 medicine that reduces appetite.</p></details>
<details><summary>How much does the Wegovy pill cost in the UK?</summary><p>Pricing is comparable to the injection.</p></details>
<details><summary>Is the Wegovy pill available in the UK?</summary><p>Yes, following MHRA approval.</p></details>
</section>""",
)

SUPERDRUG = _page(
    title="Wegovy Pill | Superdrug Online Doctor",
    desc="The Wegovy pill is a daily oral semaglutide tablet for weight loss. Learn "
         "how it works, dosing, side effects and how it compares to the injection.",
    h1="Wegovy Pill",
    body="""
<p>The Wegovy pill is a prescription-only weight loss medication containing
semaglutide, a GLP-1 receptor agonist that suppresses appetite, increases
feelings of fullness and slows stomach emptying.</p>
<h2>How to take the Wegovy pill</h2>
<p>Take it once per day in the morning on an empty stomach. Swallow the Wegovy
pill with 120ml of plain water and wait 30 minutes before eating or drinking.
In clinical trials this absorption step increased uptake by around 40%.</p>
<h2>Wegovy pill dosage</h2>
<p>The pill is taken daily in doses from 1.5mg up to 25mg, increased gradually.
The injection by contrast is weekly, from 0.25mg to 7.2mg.</p>
<h2>Wegovy pill results and the OASIS trial</h2>
<p>In the OASIS 4 trial average weight loss at the 25mg dose was 16.6% over
64 weeks. The Wegovy pill has been approved by the MHRA.</p>
<h2>Side effects</h2>
<p>Common side effects include nausea, vomiting, diarrhoea and constipation.</p>
<h2>Wegovy and heart health</h2>
<p>Semaglutide has proven cardiovascular benefits, reducing the risk of heart
attack and stroke in some patients.</p>
<h2>Wegovy pill vs injection and vs Ozempic</h2>
<p>Compared to the injection the pill avoids needles. Ozempic contains the same
drug but is licensed for type 2 diabetes.</p>
""",
    ld="""{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
{"@type":"Question","name":"Can I buy the Wegovy pill on the NHS?","acceptedAnswer":{"@type":"Answer","text":"Not currently."}},
{"@type":"Question","name":"Is the Wegovy pill safe?","acceptedAnswer":{"@type":"Answer","text":"It is prescription-only and assessed by a clinician."}},
{"@type":"Question","name":"Who can take the Wegovy pill?","acceptedAnswer":{"@type":"Answer","text":"Adults meeting BMI criteria."}}
]}""",
)

VOY = _page(
    title="Buy Wegovy Pill UK | Weight Loss Tablets | Voy",
    desc="The Wegovy pill is a once-daily oral semaglutide tablet from Novo Nordisk. "
         "See how the first oral GLP-1 for weight loss works, dosing and results.",
    h1="Wegovy Pill (Oral Semaglutide)",
    body="""
<p>The Wegovy pill is a once-daily tablet from Novo Nordisk containing
semaglutide, the same active ingredient as the Wegovy injection. It is a GLP-1
receptor agonist, mimicking the gut hormone GLP-1 your body releases when you
eat, which reduces appetite.</p>
<h2>The first oral GLP-1 for weight loss</h2>
<p>The Wegovy pill became the first oral weight loss medicine of its kind,
approved by the MHRA. Patients start low and increase through 1.5mg, 4mg, 9mg
and 25mg tablets.</p>
<h2>Wegovy pill results</h2>
<p>The Wegovy pill produces an average of 16.6% weight loss over 64 weeks at the
25mg dose.</p>
<h2>Wegovy pill vs orforglipron</h2>
<p>A rival oral GLP-1, orforglipron (Foundayo), is also in development. Unlike
orforglipron, oral semaglutide is a peptide and needs an empty stomach.</p>
<h2>BMI eligibility</h2>
<p>You may be eligible with a BMI of 30, or 27 with a weight-related condition.</p>
""",
    faqs_html="""
<section><h2>Questions</h2>
<details><summary>What is the difference between Rybelsus and the Wegovy pill?</summary><p>Rybelsus is oral semaglutide licensed for type 2 diabetes; the Wegovy pill is licensed for weight loss.</p></details>
<details><summary>Can I switch from the injection to the pill?</summary><p>Speak to your prescriber.</p></details>
<details><summary>How long until the Wegovy pill works?</summary><p>Appetite effects begin within weeks.</p></details>
</section>""",
)

PHARMICA = _page(
    title="Wegovy® Oral Pill (Semaglutide Tablets) For Weight Loss | Pharmica",
    desc="Wegovy oral tablets are a daily semaglutide pill for weight loss. Learn how "
         "the SNAC absorption enhancer works, BMI eligibility and dosage.",
    h1="Wegovy Oral Tablet (Semaglutide Tablets)",
    body="""
<p>Wegovy semaglutide tablets are an oral formulation of semaglutide for
once-daily administration. They are co-formulated with an absorption enhancer,
SNAC (sodium N-(8-[2-hydroxybenzoyl]amino) caprylate), which helps the peptide
survive the stomach.</p>
<h2>How Wegovy tablets work</h2>
<p>Semaglutide is a GLP-1 receptor agonist. It increases insulin secretion,
improves blood glucose control and reduces appetite. The oral formulation was
first approved by the FDA in 2019 as Rybelsus for type 2 diabetes.</p>
<h2>BMI eligibility</h2>
<p>Treatment is intended for adults with a BMI of 30 kg/m² or more, or 27 kg/m²
with a weight-related comorbidity.</p>
<h2>Wegovy tablets dosage</h2>
<p>The dose is increased gradually to a 25mg maintenance dose taken on an empty
stomach with a little water.</p>
<h2>Wegovy tablets vs Orlistat and Ozempic</h2>
<p>Unlike orlistat, semaglutide works on appetite. Ozempic is the diabetes brand
of injectable semaglutide.</p>
""",
    ld="""{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
{"@type":"Question","name":"Are Wegovy tablets as effective as the injection?","acceptedAnswer":{"@type":"Answer","text":"Trials show comparable weight loss."}},
{"@type":"Question","name":"What is SNAC in the Wegovy pill?","acceptedAnswer":{"@type":"Answer","text":"An absorption enhancer."}},
{"@type":"Question","name":"Can I take Wegovy tablets with other medicines?","acceptedAnswer":{"@type":"Answer","text":"Check with your prescriber."}}
]}""",
)

BOOTS = _page(
    title="Wegovy | Boots Online Doctor",
    desc="Wegovy is a semaglutide weight loss treatment, available as a weekly "
         "injection and now a daily pill. Prescription-only after assessment.",
    h1="Wegovy",
    body="""
<p>Wegovy is a semaglutide weight loss treatment. It is available as a weekly
injection and now as a once-daily pill. It is a prescription-only medicine and
requires an online consultation with a prescriber.</p>
<h2>Who can take Wegovy</h2>
<p>Adults with a BMI of 30, or 27 with a weight-related condition, may be
eligible. Semaglutide reduces appetite and slows gastric emptying.</p>
<h2>Side effects</h2>
<p>Side effects include nausea and other gastrointestinal effects.</p>
<h2>Wegovy vs Mounjaro</h2>
<p>Mounjaro (tirzepatide) is an alternative weight loss injection.</p>
""",
    faqs_html="""
<section><h2>FAQs</h2>
<details><summary>Is Wegovy available on the NHS?</summary><p>Access is limited.</p></details>
<details><summary>How much weight can I lose on Wegovy?</summary><p>Results vary.</p></details>
</section>""",
)

WEGOVY_RESULTS = _page(
    title="Wegovy Pill Results | Wegovy®",
    desc="See clinical results for the Wegovy pill (oral semaglutide), including "
         "average weight loss in the OASIS trial programme.",
    h1="Wegovy Pill Results",
    body="""
<p>The Wegovy pill is oral semaglutide from Novo Nordisk. In the OASIS clinical
trial programme, the absorption enhancer SNAC enables the semaglutide peptide to
be absorbed as a tablet.</p>
<h2>Clinical results</h2>
<p>Average weight loss was around 16.6% over 64 weeks at the maintenance dose,
measured as a percentage of body weight.</p>
<h2>How it works</h2>
<p>Semaglutide is a GLP-1 receptor agonist that reduces appetite and slows
gastric emptying. Wegovy also has cardiovascular benefits.</p>
""",
)

WEGOVY_HOME = _page(
    title="Wegovy® (semaglutide) | Official Site",
    desc="Wegovy (semaglutide) for weight management. Available as an injection and "
         "as an oral pill. Prescription-only.",
    h1="Wegovy® (semaglutide)",
    body="""
<p>Wegovy is semaglutide, a GLP-1 receptor agonist from Novo Nordisk for weight
management, available as an injection and as an oral pill. Prescription-only.</p>
<h2>About Wegovy</h2>
<p>Wegovy reduces appetite. Talk to a healthcare provider about whether it is
right for you.</p>
""",
)

FIXTURE_PAGES = {
    "https://www.simpleonlinepharmacy.co.uk/weight-loss/wegovy-pill": SOP,
    "https://onlinedoctor.superdrug.com/wegovy-pill.html": SUPERDRUG,
    "https://www.joinvoy.com/weight-loss/medications/wegovy-pill": VOY,
    "https://www.pharmica.co.uk/weight-loss/wegovy-oral-tablet": PHARMICA,
    "https://onlinedoctor.boots.com/treatments/wegovy": BOOTS,
    "https://www.wegovy.com/obesity/is-wegovy-right-for-me/wegovy-pill-results.html": WEGOVY_RESULTS,
    "https://www.wegovy.com": WEGOVY_HOME,
}
