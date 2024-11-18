import re

from src.core.media_types import MediaCategories

RE_MATCH = re.compile(r"(mediatype|filetype|path|tag):(\"?[A-Za-z0-9 \t]+\"?)?")


class SearchAutoFill:
    def __init__(self, search_field_model, library):
        self.search_field_model = search_field_model
        self.lib = library

    def update_completions_list(self, text: str) -> None:
        matches = RE_MATCH.match(text)

        completion_list = []
        if len(text) < 3:
            completion_list = ["mediatype:", "filetype:", "path:", "tag:"]
            self.search_field_model.setStringList(completion_list)

        if not matches:
            return

        query_type, query_value = matches.groups()

        if not query_value:
            return

        if query_type == "tag":
            completion_list = list(map(lambda x: f"tag:{x.name}", self.lib.tags))
        elif query_type == "path":
            completion_list = list(map(lambda x: f"path:{x}", self.lib.get_paths()))
        elif query_type == "mediatype":
            single_word_completions = map(
                lambda x: f"mediatype:{x.media_type.value}",
                filter(lambda y: " " not in y.media_type.value, MediaCategories.ALL_CATEGORIES),
            )
            single_word_completions_quoted = map(
                lambda x: f'mediatype:"{x.media_type.value}"',
                filter(lambda y: " " not in y.media_type.value, MediaCategories.ALL_CATEGORIES),
            )
            multi_word_completions = map(
                lambda x: f'mediatype:"{x.media_type.value}"',
                filter(lambda y: " " in y.media_type.value, MediaCategories.ALL_CATEGORIES),
            )

            all_completions = [
                single_word_completions,
                single_word_completions_quoted,
                multi_word_completions,
            ]
            completion_list = [j for i in all_completions for j in i]
        elif query_type == "filetype":
            extensions_list: set[str] = set()
            for media_cat in MediaCategories.ALL_CATEGORIES:
                extensions_list = extensions_list | media_cat.extensions
            completion_list = list(map(lambda x: f"filetype:{x.lstrip('.')}", extensions_list))

        update_completion_list: bool = (
            completion_list != self.search_field_model.stringList() or self.search_field_model == []
        )

        if update_completion_list:
            self.search_field_model.setStringList(completion_list)
