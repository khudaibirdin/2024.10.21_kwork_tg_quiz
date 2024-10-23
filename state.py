from aiogram.fsm.state import State, StatesGroup


class CommonStates(StatesGroup):
    quiz_mode_await = State()
    period_await = State()
    channel_id_await = State()