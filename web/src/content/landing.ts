import type {
  ToileAbout,
  ToileColumn,
  ToileContact,
  ToileContactBand,
  ToileHero,
  ToileLink,
  ToileNote,
  ToilePress,
  ToileSectionCopy,
  ToileService,
  ToileSolution,
} from "@/components/ui/cobalt-toile-landing"

/*
 * Every word on the landing page. Nothing here is invented: these are the words the team
 * wrote for the page, and the page says only what is planned now.
 */

export const REPO_URL = "https://github.com/Hasan-Mustafa-Rizvi/Argos"
export const CREDITS_URL = REPO_URL + "#credits"
export const SIGN_IN = "/sign-in"

export const brand = "Argos"
export const monogram = "A"

export const nav: ToileLink[] = [
  { label: "About", href: "#about" },
  { label: "What it does", href: "#solutions" },
  { label: "Questions", href: "#services" },
  { label: "Who made this", href: "#insights" },
]

export const cta: ToileLink = { label: "Open the dashboard", href: SIGN_IN }

export const hero: ToileHero = {
  title: "Someone to\nkeep watch.",
  subtitle:
    "Argos is a companion that stays in the room, notices when something is wrong, asks first, and sends word home only when it must.",
  action: { label: "Open the dashboard", href: SIGN_IN },
  est: "HackUTA MMXXVI",
  edition: "Arlington · Ithaca",
}

export const clientsLabel = "Built with"
export const clients = ["Raspberry Pi", "Reachy Mini", "Supabase", "Gemini", "ElevenLabs", "Chert", "React"]

export const about: ToileAbout = {
  kicker: "The idea",
  statement: "Everything else waits for the person to *do something*. Argos notices when they can't.",
  body: "A watch has to be worn and charged. A pendant has to be pressed. A camera only watches. Argos sits in the room the way a dog would, and checks on the person itself before it worries anyone.",
  stats: [
    { value: 0, label: "Things to wear" },
    { value: 10, suffix: " s", label: "To answer before Argos calls" },
    { value: 1, label: "Image kept, and only if a check fails" },
  ],
  seal: "Argos · keeps watch · sends word · ",
}

export const solutionsCopy: ToileSectionCopy = {
  kicker: "What it does",
  title: "Four things, *in order*",
  intro: "Pick a bookmark to read each step.",
}

const toDashboard: ToileLink = { label: "Open the dashboard", href: SIGN_IN }

export const solutions: ToileSolution[] = [
  {
    title: "Watches",
    quote: "Nothing to wear. Nothing to press.",
    body: "Argos glances at the person now and then and listens. It notices someone on the floor, a call for help, or a long stillness.",
    art: "tower",
    tone: "paper",
    action: toDashboard,
  },
  {
    title: "Checks",
    quote: "Are you okay?",
    body: "Before it tells anyone, Argos turns to the person and asks. Most alarms are false. This is where they end.",
    art: "typewriter",
    tone: "ink",
    action: toDashboard,
  },
  {
    title: "Stands down",
    quote: "I'm fine.",
    body: "An answer or a pat on the head is enough. No image is kept and nobody is called.",
    art: "monogram",
    tone: "paper",
    action: toDashboard,
  },
  {
    title: "Escalates",
    quote: "Word reaches home.",
    body: "If no answer comes, Argos video calls the emergency contact with what it sees, sends a backup email, and updates this dashboard for family and clinicians.",
    art: "steamer",
    tone: "ink",
    action: toDashboard,
  },
]

export const servicesCopy: ToileSectionCopy = {
  kicker: "Questions",
  title: "Why not something *simpler*?",
  // The template prints an intro under every section head; an empty one keeps its default out.
  intro: "",
}

export const services: ToileService[] = [
  {
    title: "Why not a watch?",
    summary: "It has to be worn.",
    details:
      "A watch helps people who wear one and charge it every night. It comes off in the shower and at bedtime, which is when falls happen. Argos is for the person who won't wear it.",
  },
  {
    title: "Why not a phone app?",
    summary: "The phone is across the room.",
    details: "After a fall the phone is on the table. An app waits to be opened.",
  },
  {
    title: "Why not a pendant?",
    summary: "It needs a button press.",
    details: "From someone who may be confused or unconscious.",
  },
  {
    title: "Why not a camera?",
    summary: "It only watches.",
    details: "A camera cannot ask 'are you okay?', and it cannot tell family when to look. Argos does both.",
  },
  {
    title: "What about privacy?",
    summary: "Nothing is recorded.",
    details:
      "The live view opens only for family who have signed in and passed a second step. One image is kept, and only when a check has failed. Family and clinicians see different things.",
  },
]

export const pressCopy: ToileSectionCopy = {
  kicker: "Who made this",
  // The template prints this heading as written, without the *italic* marker the other headings
  // read, so the asterisks are left out rather than printed.
  title: "Three people, twenty-four hours",
}

export const press: ToilePress[] = [
  {
    title: "Hasan Mustafa Rizvi",
    source: "Software, design, interface polish and organization",
    date: "HackUTA 2026",
    category: "Software and design",
    href: "https://github.com/Hasan-Mustafa-Rizvi",
  },
  {
    title: "Neel",
    source: "Hardware and the dog's body",
    date: "HackUTA 2026",
    category: "Hardware",
    href: "https://github.com/NeelM1",
  },
  {
    title: "Farrell",
    source: "Hardware and the dog's body",
    date: "HackUTA 2026",
    category: "Hardware",
    href: "https://github.com/DummyTech",
  },
]

/** In the template's order: temple, Justice, satellite, pylon. */
export const notes: ToileNote[] = [
  { title: "Ithaca", body: "Home. The place the person wants to stay." },
  { title: "The rule", body: "No image is stored unless a check fails." },
  { title: "Word home", body: "A video call to family, with what Argos sees." },
  { title: "The body", body: "A Reachy Mini robot is its eyes, ears and voice. A Raspberry Pi does the thinking." },
]

export const contactBand: ToileContactBand = {
  title: "Someone is *keeping watch*.",
  body: "Open the demo as family or as a clinician.",
  action: { label: "Open the dashboard", href: SIGN_IN },
  secondary: { label: "Read the code", href: REPO_URL },
}

export const tagline = "A companion robot dog that keeps watch and sends word. Built at HackUTA 2026."

export const contact: ToileContact = { email: "", phone: "", location: "UT Arlington" }

export const columns: ToileColumn[] = [
  {
    title: "Argos",
    links: [
      { label: "About", href: "#about" },
      { label: "What it does", href: "#solutions" },
      { label: "Questions", href: "#services" },
      { label: "Who made this", href: "#insights" },
      { label: "Read the code", href: REPO_URL },
    ],
  },
]

export const CREDIT_LINE =
  "Landing built on Cobalt Toile by Kedhareswer Naidu. Logo reveal after Glass Icon Reveal by Zanwei Guo."

/**
 * The footer credit. `legal` is the template's only full-width line in the footer bar, and it
 * prints every entry as a link, so the sentence links to the credits as well.
 */
export const legal: ToileLink[] = [
  { label: CREDIT_LINE, href: CREDITS_URL },
  { label: "Credits", href: CREDITS_URL },
]
