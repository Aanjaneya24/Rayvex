
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel


class FakeToolCallingChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self
