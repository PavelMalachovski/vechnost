"""What taking a partner's seat does, the same behind all three doors.

A room, the compatibility test and «69 ступеней» each seat their guest by an
invite link, with one conditional UPDATE. Three things follow from that one
moment, whichever door it was, and they live here so the doors cannot drift
apart:

- **The pair is kept.** Each of the two becomes the other's partner
  (`users.partner_telegram_user_id`, both ways, the latest wins), so the
  product knows who plays with whom outside any one game. `/delete_me`
  clears the link on the other side.
- **An invite is an invitation.** A newcomer seated by a link is credited
  to whoever sent it (`UserRepository.record_invite`): it counts in the
  inviter's /invite, and prices nothing - the referral price belongs to the
  `ref_` links.
- **The creator hears about it** (`partner_notify.py`), after the commit:
  someone who shared a link and closed the app would otherwise never learn
  the partner came.

Called by the join endpoints inside their transaction, right after the
guest is seated; never for a creator re-opening their own game.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .repositories import UserRepository


@dataclass(frozen=True)
class Seated:
    """Who took which seat, for the push to the creator."""

    screen: str  # the Mini App screen the game opens on: coop, compat, steps69
    code: str
    creator_id: int
    guest_name: str | None


async def seat_taken(
    session: AsyncSession,
    *,
    screen: str,
    code: str,
    creator_id: int,
    creator_name: str | None,
    guest_id: int,
    guest_name: str | None,
) -> Seated:
    """Record what a guest taking the seat means, in the join's transaction."""
    # Both rows, in case either person never opened the app since rows are
    # made at boot (`POST /api/me`), or opened it before that existed.
    await UserRepository.ensure(session, creator_id, first_name=creator_name)
    await UserRepository.ensure(session, guest_id, first_name=guest_name)
    await UserRepository.pair(session, creator_id, guest_id)
    await UserRepository.record_invite(session, guest_id, creator_id)
    return Seated(screen=screen, code=code, creator_id=creator_id, guest_name=guest_name)
