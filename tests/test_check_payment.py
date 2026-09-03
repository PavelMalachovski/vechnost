"""«Проверить статус оплаты» must answer its callback query exactly once.

`handlers.handle_callback_query` answers every query before dispatching.
The payment handler then answered it a second time, which Telegram rejects
("query is too old … or query ID is invalid"); the BadRequest escaped to the
registry's catch-all and the person who had just paid was shown
«неизвестная команда» instead of «Доступ предоставлен». The mock below
does what Telegram does: the second answer raises.
"""

from unittest.mock import AsyncMock, patch

from telegram.error import BadRequest

from vechnost_bot.handlers import handle_callback_query
from vechnost_bot.i18n import Language, get_text


async def test_the_check_payment_button_answers_its_query_once(
    mock_update, mock_callback_query, mock_context
):
    mock_callback_query.data = "check_payment"
    mock_callback_query.answer = AsyncMock(
        side_effect=[None, BadRequest("Query is too old and response timeout expired")]
    )
    with (
        patch("vechnost_bot.payments.handlers.check_and_register_user", AsyncMock()),
        patch("vechnost_bot.payments.handlers.user_has_access", AsyncMock(return_value=True)),
    ):
        await handle_callback_query(mock_update, mock_context)

    assert mock_callback_query.answer.await_count == 1
    shown = mock_callback_query.edit_message_text.await_args.args[0]
    assert shown == get_text("payment.access_granted", Language.RUSSIAN)


async def test_an_unpaid_user_gets_the_paywall_back(
    mock_update, mock_callback_query, mock_context
):
    mock_callback_query.data = "check_payment"
    with (
        patch("vechnost_bot.payments.handlers.check_and_register_user", AsyncMock()),
        patch("vechnost_bot.payments.handlers.user_has_access", AsyncMock(return_value=False)),
        patch(
            "vechnost_bot.payments.handlers.get_payment_keyboard",
            AsyncMock(return_value=None),
        ),
    ):
        await handle_callback_query(mock_update, mock_context)

    shown = mock_callback_query.edit_message_text.await_args.args[0]
    assert shown == get_text("payment.no_active_payment", Language.RUSSIAN)
