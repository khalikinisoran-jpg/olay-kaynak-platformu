from dataclasses import replace


class MemoryService:

    def set(
        self,
        state,
        key,
        value
    ):

        memory = dict(state.memory)

        memory[key] = value

        return replace(
            state,
            memory=memory
        )

    def get(
        self,
        state,
        key,
        default=None
    ):

        return state.memory.get(
            key,
            default
        )

    def exists(
        self,
        state,
        key
    ):

        return key in state.memory

    def delete(
        self,
        state,
        key
    ):

        memory = dict(state.memory)

        memory.pop(
            key,
            None
        )

        return replace(
            state,
            memory=memory
        )

    def all(
        self,
        state
    ):

        return dict(
            state.memory
        )