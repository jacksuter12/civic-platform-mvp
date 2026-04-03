"""
Seed script — realistic discussion data for all five threads.
Run from backend/: python seed.py

Safe to re-run: checks existence before inserting.
"""
import asyncio
import uuid

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.domain import Domain
from app.models.post import Post
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User, UserTier
from app.models.thread import Thread, ThreadStatus
from app.models.signal import Signal, SignalType
from app.models.vote import Vote, VoteChoice


DOMAIN_SLUG = "healthcare"

THREADS = [
    {
        "title": "Should our city fund mobile mental health crisis teams?",
        "prompt": (
            "The current model sends police to mental health calls. "
            "Should the city fund a dedicated mobile crisis team staffed by "
            "clinicians instead? What should the scope, budget, and oversight look like?"
        ),
        "context": (
            "In 2023, 34% of 911 calls involving a mental health component resulted "
            "in an arrest. A pilot mobile crisis program in Denver reduced arrests in "
            "similar calls by 67% over two years."
        ),
        "status": ThreadStatus.DELIBERATING,
        "signals": [
            (SignalType.SUPPORT, 8),
            (SignalType.CONCERN, 3),
            (SignalType.NEED_INFO, 5),
        ],
    },
    {
        "title": "Expanding rural telehealth access: who pays and how?",
        "prompt": (
            "Rural residents face provider shortages and long travel distances for care. "
            "Should the county negotiate a subsidized telehealth contract, and if so, "
            "how should costs be shared between the county, insurers, and patients?"
        ),
        "context": (
            "The nearest specialist is 90 miles from three of our rural zip codes. "
            "Broadband penetration in those areas is 71% as of 2024."
        ),
        "status": ThreadStatus.PROPOSING,
        "signals": [
            (SignalType.SUPPORT, 14),
            (SignalType.CONCERN, 2),
        ],
    },
    {
        "title": "Mandatory nurse-to-patient ratios at county hospitals",
        "prompt": (
            "California's mandated ratios reduced patient mortality. Should our county "
            "hospitals adopt similar mandates? What ratios are appropriate, and what "
            "is the staffing and budget impact?"
        ),
        "context": "",
        "status": ThreadStatus.OPEN,
        "signals": [],
    },
    {
        "title": "Free naloxone distribution at public libraries",
        "prompt": (
            "Overdose deaths in the county rose 22% last year. Should the public library "
            "system distribute naloxone kits, and should staff receive training to administer them?"
        ),
        "context": (
            "The county health department has offered to supply kits at no cost to the library "
            "system. Staff union has raised liability concerns."
        ),
        "status": ThreadStatus.VOTING,
        "signals": [
            (SignalType.SUPPORT, 21),
            (SignalType.CONCERN, 4),
            (SignalType.BLOCK, 1),
        ],
    },
    {
        "title": "Co-pay elimination for preventive screenings",
        "prompt": (
            "Should the county employee health plan eliminate co-pays for preventive "
            "screenings (mammograms, colonoscopies, A1C tests)? What is the projected "
            "cost and long-term savings estimate?"
        ),
        "context": "",
        "status": ThreadStatus.CLOSED,
        "signals": [
            (SignalType.SUPPORT, 31),
            (SignalType.CONCERN, 6),
            (SignalType.NEED_INFO, 2),
        ],
    },
]


async def get_thread(db, title_prefix):
    r = await db.execute(select(Thread).where(Thread.title.startswith(title_prefix)))
    return r.scalar_one_or_none()


async def has_posts(db, thread):
    r = await db.execute(select(Post).where(Post.thread_id == thread.id))
    return r.scalars().first() is not None


async def has_proposals(db, thread):
    r = await db.execute(select(Proposal).where(Proposal.thread_id == thread.id))
    return r.scalars().first() is not None


async def seed():
    async with AsyncSessionLocal() as db:

        # ── 1. Domain ──────────────────────────────────────────────────────────
        r = await db.execute(select(Domain).where(Domain.slug == DOMAIN_SLUG))
        domain = r.scalar_one_or_none()
        if not domain:
            domain = Domain(
                slug=DOMAIN_SLUG,
                name="Healthcare",
                description="Public health policy deliberations for the county.",
                is_active=True,
            )
            db.add(domain)
            await db.flush()
            print(f"Created domain: {domain.name}")
        else:
            print(f"Domain exists: {domain.name}")

        # ── 2. Facilitator ─────────────────────────────────────────────────────
        r = await db.execute(select(User).where(User.email == "seed@civic.local"))
        facilitator = r.scalar_one_or_none()
        if not facilitator:
            facilitator = User(
                supabase_uid=str(uuid.uuid4()),
                email="seed@civic.local",
                display_name="Seed Facilitator",
                tier=UserTier.FACILITATOR,
                is_active=True,
            )
            db.add(facilitator)
            await db.flush()
            print(f"Created facilitator: {facilitator.display_name}")
        else:
            print(f"Facilitator exists: {facilitator.display_name}")

        # ── 3. Participant pool (35 users) ─────────────────────────────────────
        users = []
        names = [
            "Maya R.", "Theo K.", "Priya S.", "Jordan L.", "Sam W.",
            "Aisha M.", "Devon C.", "Nora H.", "Eli B.", "Rosa F.",
            "Chris T.", "Leila N.", "Omar J.", "Fiona D.", "Marcus P.",
            "Zara A.", "Ben O.", "Camille V.", "Dante G.", "Iris X.",
            "Felix U.", "Hana Q.", "Ivan Y.", "Juno Z.", "Kai E.",
            "Lena I.", "Milo R.", "Nina S.", "Otto K.", "Pia L.",
            "Quinn M.", "Rex N.", "Sage O.", "Tara P.", "Uma Q.",
        ]
        for i in range(35):
            email = f"participant{i}@civic.local"
            r = await db.execute(select(User).where(User.email == email))
            u = r.scalar_one_or_none()
            if not u:
                u = User(
                    supabase_uid=str(uuid.uuid4()),
                    email=email,
                    display_name=names[i],
                    tier=UserTier.PARTICIPANT,
                    is_active=True,
                )
                db.add(u)
                await db.flush()
            users.append(u)

        # ── 4. Threads + signals ───────────────────────────────────────────────
        for t_data in THREADS:
            r = await db.execute(select(Thread).where(Thread.title == t_data["title"]))
            thread = r.scalar_one_or_none()
            if not thread:
                thread = Thread(
                    domain_id=domain.id,
                    created_by_id=facilitator.id,
                    title=t_data["title"],
                    prompt=t_data["prompt"],
                    context=t_data["context"],
                    status=t_data["status"],
                )
                db.add(thread)
                await db.flush()
                user_idx = 0
                for signal_type, count in t_data["signals"]:
                    for _ in range(count):
                        if user_idx < len(users):
                            db.add(Signal(
                                thread_id=thread.id,
                                user_id=users[user_idx].id,
                                signal_type=signal_type,
                            ))
                            user_idx += 1
                print(f"Created thread: {thread.title[:55]}… [{thread.status.value}]")
            else:
                print(f"Thread exists:  {thread.title[:55]}…")

        await db.flush()

        # ── 5. Posts: DELIBERATING — mobile mental health ──────────────────────
        t1 = await get_thread(db, "Should our city fund mobile mental health")
        if t1 and not await has_posts(db, t1):
            p1 = Post(thread_id=t1.id, author_id=users[0].id, body=(
                "The Denver data is compelling — 67% reduction in arrests for "
                "mental health calls is hard to dismiss. My main question is "
                "whether clinicians would be safe responding without police backup. "
                "What does the research say on co-response vs fully independent teams?"
            ))
            db.add(p1); await db.flush()

            db.add(Post(thread_id=t1.id, author_id=users[2].id, parent_id=p1.id, body=(
                "CAHOOTS in Eugene has operated independently since 1989 — no police, "
                "strong safety record. The key is dispatch triage: they only respond "
                "to calls where no weapons report has been filed."
            )))

            p2 = Post(thread_id=t1.id, author_id=users[1].id, body=(
                "I support this in principle but we need a sustainability plan. "
                "Pilots often run on grant money and collapse when it runs out. "
                "What's the long-term funding source — general fund, levy, or grants?"
            ))
            db.add(p2); await db.flush()

            db.add(Post(thread_id=t1.id, author_id=users[3].id, parent_id=p2.id, body=(
                "This is my main concern too. The county health dept said they'd cover "
                "year one, but years two and three are unspecified. We should require "
                "a three-year funding plan as a precondition for approval."
            )))

            db.add(Post(thread_id=t1.id, author_id=users[4].id, body=(
                "Has anyone looked at what staff we'd actually need? Our county has a "
                "serious shortage of licensed mental health clinicians. If we can't "
                "hire the staff, the plan is moot regardless of funding."
            )))

            db.add(Post(thread_id=t1.id, author_id=users[5].id, body=(
                "Worth flagging: the 34% arrest rate in our 911 data almost certainly "
                "undercounts. Many callers don't disclose that a mental health crisis "
                "is involved. The real scope of the problem is probably larger."
            )))
            await db.flush()
            print("  → Posts added (DELIBERATING thread)")

        # ── 6. Posts: PROPOSING — rural telehealth ─────────────────────────────
        t2 = await get_thread(db, "Expanding rural telehealth access")
        if t2 and not await has_posts(db, t2):
            p1 = Post(thread_id=t2.id, author_id=users[6].id, body=(
                "The provider shortage is real — I've seen patients drive 90 miles "
                "for a 20-minute specialist appointment. Telehealth won't replace "
                "everything but for psychiatry, dermatology, and most follow-ups "
                "it works well. We should focus the contract on high-volume "
                "specialty referrals first."
            ))
            db.add(p1); await db.flush()

            db.add(Post(thread_id=t2.id, author_id=users[8].id, parent_id=p1.id, body=(
                "Agreed on dermatology and psych. I'd add chronic disease management "
                "— A1C monitoring, blood pressure follow-ups. These are high frequency, "
                "low acuity, and the travel burden is significant for rural patients."
            )))

            p2 = Post(thread_id=t2.id, author_id=users[7].id, body=(
                "The 29% broadband gap worries me. Any county contract needs a "
                "voice/phone fallback — not everyone has reliable video. "
                "Have we looked at what platforms offer low-bandwidth modes?"
            ))
            db.add(p2); await db.flush()

            db.add(Post(thread_id=t2.id, author_id=users[9].id, parent_id=p2.id, body=(
                "Most enterprise telehealth platforms have audio-only modes. "
                "The bigger issue is reimbursement — CMS has expanded audio-only "
                "coverage post-COVID but it's still patchwork for commercial payers."
            )))

            db.add(Post(thread_id=t2.id, author_id=users[10].id, body=(
                "Whoever negotiates this contract needs to publish the pricing terms. "
                "Some counties have signed telehealth deals that cost more than "
                "in-person care once you factor in platform fees and per-visit charges. "
                "Transparency should be a contract requirement."
            )))
            await db.flush()
            print("  → Posts added (PROPOSING thread)")

        # ── 7. Proposals: PROPOSING — rural telehealth ─────────────────────────
        if t2 and not await has_proposals(db, t2):
            db.add(Proposal(
                thread_id=t2.id,
                created_by_id=users[6].id,
                title="County-negotiated telehealth platform with sliding-scale patient fees",
                description=(
                    "The county contracts with a HIPAA-compliant telehealth platform "
                    "and subsidises access for rural residents on a sliding scale tied "
                    "to income. Patients at or below 200% FPL pay nothing; those above "
                    "pay a co-pay capped at $15 per visit. The county covers platform "
                    "licensing costs (~$180k/year estimated) from the public health budget. "
                    "Contract must include audio-only fallback, annual pricing transparency "
                    "report, and a 3-year term with renewal contingent on utilisation data."
                ),
                status=ProposalStatus.SUBMITTED,
                requested_amount=None,
            ))

            db.add(Proposal(
                thread_id=t2.id,
                created_by_id=users[7].id,
                title="Hybrid model: telehealth platform plus quarterly mobile clinic days",
                description=(
                    "Combines a county telehealth contract with four mobile clinic visits "
                    "per year to each underserved zip code. The mobile clinics handle "
                    "screenings and procedures that can't be done remotely; telehealth "
                    "covers follow-ups and specialist consultations. Estimated cost: "
                    "$240k/year for telehealth licensing plus $80k for mobile clinic "
                    "operations. Funding split: 60% county public health budget, "
                    "40% federal Rural Health Care Program reimbursement."
                ),
                status=ProposalStatus.SUBMITTED,
                requested_amount=None,
            ))
            await db.flush()
            print("  → Proposals added (PROPOSING thread)")

        # ── 8. Posts: OPEN — nurse-to-patient ratios ───────────────────────────
        t3 = await get_thread(db, "Mandatory nurse-to-patient ratios")
        if t3 and not await has_posts(db, t3):
            p1 = Post(thread_id=t3.id, author_id=users[11].id, body=(
                "California's 1:5 ratio in med-surg units has been in effect since "
                "2004. The mortality evidence is strong — roughly a 5% reduction in "
                "30-day mortality per additional nurse. But the staffing cost increase "
                "was around 14% when it was first implemented. We need to model that "
                "for our county hospitals before we commit."
            ))
            db.add(p1); await db.flush()

            db.add(Post(thread_id=t3.id, author_id=users[13].id, parent_id=p1.id, body=(
                "The 14% figure is the short-term implementation cost. The longer-term "
                "picture includes reduced adverse events, shorter stays, and lower "
                "agency nurse spending. California hospitals that modelled this "
                "over ten years found net savings in most cases."
            )))

            p2 = Post(thread_id=t3.id, author_id=users[12].id, body=(
                "As a nurse working county hospitals for eleven years: unsafe ratios "
                "are driving experienced staff out faster than we can train replacements. "
                "I've watched three colleagues leave for agency work in the last year "
                "alone — better pay, more control over hours, same work. "
                "A mandate pays for itself in retention."
            ))
            db.add(p2); await db.flush()

            db.add(Post(thread_id=t3.id, author_id=users[14].id, parent_id=p2.id, body=(
                "This is the strongest argument for the mandate in my view. "
                "Agency nurse costs are enormous — often 2-3x base salary when "
                "you include agency fees. If a ratio mandate reduces agency dependency "
                "by 20%, it might be cost-neutral within two years."
            )))

            db.add(Post(thread_id=t3.id, author_id=users[15].id, body=(
                "We should consider unit-specific ratios rather than a blanket rule. "
                "ICU needs are very different from outpatient surgical recovery. "
                "California uses different ratios by unit type — that's probably the "
                "right model rather than a single number for all settings."
            )))
            await db.flush()
            print("  → Posts added (OPEN thread)")

        # ── 9. Posts: VOTING — naloxone at libraries ───────────────────────────
        t4 = await get_thread(db, "Free naloxone distribution at public libraries")
        if t4 and not await has_posts(db, t4):
            p1 = Post(thread_id=t4.id, author_id=users[16].id, body=(
                "Libraries are already de facto community health hubs — they do "
                "diabetes screenings, blood pressure checks, and host AA meetings. "
                "Naloxone distribution is a natural extension. The Multnomah County "
                "library system has done this since 2017 with no significant incidents "
                "and staff reporting stronger community trust as a result."
            ))
            db.add(p1); await db.flush()

            db.add(Post(thread_id=t4.id, author_id=users[18].id, parent_id=p1.id, body=(
                "The Multnomah example is useful. Worth noting their staff went through "
                "a 3-hour training programme run by the county health dept — not a huge "
                "lift. The liability questions were resolved through county indemnification."
            )))

            p2 = Post(thread_id=t4.id, author_id=users[17].id, body=(
                "The staff training question is the crux for me. Distributing kits "
                "passively is one thing; having staff trained and willing to administer "
                "is a meaningful ask. The union's liability concern deserves a direct "
                "legal response — county indemnification needs to be explicit and "
                "confirmed in writing before we ask staff to take that on."
            ))
            db.add(p2); await db.flush()

            db.add(Post(thread_id=t4.id, author_id=users[19].id, parent_id=p2.id, body=(
                "Agree that indemnification needs to be in writing. I'd also suggest "
                "that training be voluntary for existing staff — mandatory only for "
                "new hires going forward. That addresses the union's concerns while "
                "still building capacity over time."
            )))

            db.add(Post(thread_id=t4.id, author_id=users[20].id, body=(
                "22% rise in overdose deaths is a public health emergency. "
                "The county has already offered to supply kits at no cost. "
                "The only obstacle is administrative caution. "
                "People are dying while we deliberate — I want that in the record."
            )))
            await db.flush()
            print("  → Posts added (VOTING thread)")

        # ── 10. Proposals + votes: VOTING — naloxone ──────────────────────────
        if t4 and not await has_proposals(db, t4):
            prop_a = Proposal(
                thread_id=t4.id,
                created_by_id=users[16].id,
                title="Full library naloxone programme with voluntary staff training",
                description=(
                    "The library system distributes county-supplied naloxone kits "
                    "at all 11 branch locations. Staff training (3-hour county health "
                    "dept programme) is offered to all staff and mandatory for new hires. "
                    "County provides explicit written indemnification for staff acting "
                    "in good faith under Good Samaritan law. Kits are placed in visible "
                    "public locations, not behind the desk. Programme reviewed annually "
                    "with usage data reported to the Board of Supervisors."
                ),
                status=ProposalStatus.VOTING,
                requested_amount=None,
            )
            db.add(prop_a); await db.flush()

            prop_b = Proposal(
                thread_id=t4.id,
                created_by_id=users[17].id,
                title="Passive naloxone distribution only — no staff administration",
                description=(
                    "Naloxone kits are made available at library branches for "
                    "community members to take freely, similar to seed libraries or "
                    "free book exchanges. No staff training for administration is "
                    "required or expected. Staff are instructed to call 911 in an "
                    "emergency rather than administer. This approach addresses the "
                    "union's liability concerns while still making kits accessible. "
                    "Kits supplied at no cost by the county health department."
                ),
                status=ProposalStatus.VOTING,
                requested_amount=None,
            )
            db.add(prop_b); await db.flush()

            # Votes for proposal A (full programme): 18 yes, 3 no, 2 abstain
            vote_choices_a = (
                [VoteChoice.YES] * 18 + [VoteChoice.NO] * 3 + [VoteChoice.ABSTAIN] * 2
            )
            for i, choice in enumerate(vote_choices_a):
                db.add(Vote(
                    proposal_id=prop_a.id,
                    voter_id=users[i].id,
                    choice=choice,
                ))

            # Votes for proposal B (passive only): 8 yes, 9 no, 4 abstain
            vote_choices_b = (
                [VoteChoice.YES] * 8 + [VoteChoice.NO] * 9 + [VoteChoice.ABSTAIN] * 4
            )
            for i, choice in enumerate(vote_choices_b):
                db.add(Vote(
                    proposal_id=prop_b.id,
                    voter_id=users[i].id,
                    choice=choice,
                ))
            await db.flush()
            print("  → Proposals + votes added (VOTING thread)")

        # ── 11. Posts: CLOSED — co-pay elimination ─────────────────────────────
        t5 = await get_thread(db, "Co-pay elimination for preventive screenings")
        if t5 and not await has_posts(db, t5):
            p1 = Post(thread_id=t5.id, author_id=users[21].id, body=(
                "The actuarial case for co-pay elimination on preventive care is "
                "solid. Early detection of colorectal cancer or unmanaged diabetes "
                "costs a fraction of late-stage treatment. The question isn't whether "
                "it saves money — it does — but over what time horizon the plan "
                "sees the savings. Typically 5-7 years."
            ))
            db.add(p1); await db.flush()

            db.add(Post(thread_id=t5.id, author_id=users[23].id, parent_id=p1.id, body=(
                "The ACA already mandates coverage for USPSTF A/B screenings without "
                "cost-sharing for non-grandfathered plans. The county plan is grandfathered "
                "and hasn't caught up. This proposal is essentially bringing us into "
                "alignment with what most employers already offer."
            )))

            p2 = Post(thread_id=t5.id, author_id=users[22].id, body=(
                "Agreed on the economics. I'd push for limiting elimination to "
                "USPSTF A and B-rated screenings only — evidence-based, well-defined. "
                "If we include borderline or C-rated screenings we open up significant "
                "utilisation uncertainty and the cost modelling gets murky."
            ))
            db.add(p2); await db.flush()

            db.add(Post(thread_id=t5.id, author_id=users[24].id, parent_id=p2.id, body=(
                "This is the right boundary. A/B only is a defensible, coherent policy. "
                "We should also require annual reporting on screening uptake rates — "
                "if eliminating the co-pay doesn't actually increase utilisation, "
                "we should know that within year one."
            )))

            db.add(Post(thread_id=t5.id, author_id=users[25].id, body=(
                "One thing I haven't seen discussed: equity impact. Co-pay elimination "
                "helps everyone, but the people currently skipping screenings due to "
                "cost are disproportionately lower-income employees. We should track "
                "uptake by salary band to see if we're actually reaching them."
            )))
            await db.flush()
            print("  → Posts added (CLOSED thread)")

        # ── 12. Proposals + votes: CLOSED — co-pay ────────────────────────────
        if t5 and not await has_proposals(db, t5):
            prop_c = Proposal(
                thread_id=t5.id,
                created_by_id=users[21].id,
                title="Eliminate co-pays for all USPSTF A/B-rated preventive screenings",
                description=(
                    "The county employee health plan eliminates co-pays and cost-sharing "
                    "for all screenings rated A or B by the US Preventive Services Task "
                    "Force. This covers mammograms, colonoscopies, A1C tests, blood "
                    "pressure screening, depression screening, and approximately 28 other "
                    "evidence-based preventive services. Estimated net cost to the plan: "
                    "$340k/year in years 1-2, projected to be cost-neutral by year 5 "
                    "through reduced downstream treatment costs. Annual uptake report "
                    "required, disaggregated by employee salary band."
                ),
                status=ProposalStatus.PASSED,
                requested_amount=None,
            )
            db.add(prop_c); await db.flush()

            prop_d = Proposal(
                thread_id=t5.id,
                created_by_id=users[22].id,
                title="Pilot year: eliminate co-pays for mammograms and colonoscopies only",
                description=(
                    "A more limited first step: eliminate co-pays only for mammograms "
                    "and colonoscopies in year one, with a formal evaluation before "
                    "expanding to additional screenings. This approach limits initial "
                    "cost exposure, allows the plan to measure actual utilisation impact, "
                    "and creates a data-driven basis for expanding the programme. "
                    "Estimated cost: $95k in year one. Evaluation report due to the "
                    "benefits committee by Q3 of year one."
                ),
                status=ProposalStatus.REJECTED,
                requested_amount=None,
            )
            db.add(prop_d); await db.flush()

            # Votes for proposal C (full USPSTF): 27 yes, 4 no, 3 abstain
            vote_choices_c = (
                [VoteChoice.YES] * 27 + [VoteChoice.NO] * 4 + [VoteChoice.ABSTAIN] * 3
            )
            for i, choice in enumerate(vote_choices_c):
                db.add(Vote(
                    proposal_id=prop_c.id,
                    voter_id=users[i].id,
                    choice=choice,
                ))

            # Votes for proposal D (pilot only): 9 yes, 21 no, 4 abstain
            vote_choices_d = (
                [VoteChoice.YES] * 9 + [VoteChoice.NO] * 21 + [VoteChoice.ABSTAIN] * 4
            )
            for i, choice in enumerate(vote_choices_d):
                db.add(Vote(
                    proposal_id=prop_d.id,
                    voter_id=users[i].id,
                    choice=choice,
                ))
            await db.flush()
            print("  → Proposals + votes added (CLOSED thread)")

        await db.commit()
        print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
