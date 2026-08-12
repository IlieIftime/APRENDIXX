"""Native BeeWare/Toga iOS shell sharing the same mobile runtime."""

from __future__ import annotations

import time
import webbrowser
from pathlib import Path


def main():
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW

    from aprendix_mobile.runtime import build_mobile_runtime
    from aprendix.application.games import DIFFICULTIES, MinesweeperGame, SudokuGame

    class AprendixIOS(toga.App):
        def startup(self):
            self.runtime = build_mobile_runtime()
            self.theme = self.runtime.state.setting("theme", "dark")
            self.cards = self.runtime.cards()
            self.index = 0
            self.areas = self.runtime.areas()
            self.area_labels = {
                ("  " * int(item["depth"]) + ("↳ " if item["depth"] else "") + str(item["title"])): str(item["id"])
                for item in self.areas
            }
            self.title_label = toga.Label("", style=Pack(font_size=24, font_weight="bold", margin=10))
            self.body_label = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=10))
            self.mode = toga.Selection(items=["Recomendado", "Livre"], on_change=self.change_mode, style=Pack(flex=1))
            self.area = toga.Selection(items=["Toda a árvore", *self.area_labels], on_change=self.change_mode, style=Pack(flex=2, margin_left=6))
            toolbar = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                self.mode,
                self.area,
                toga.Button("Pesquisa", on_press=self.show_search, style=Pack(margin_left=8)),
                toga.Button("Games", on_press=self.show_games, style=Pack(margin_left=8)),
                toga.Button("Claro/Escuro", on_press=self.toggle_contrast, style=Pack(margin_left=8)),
            ])
            learning_toolbar = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("Curso", on_press=self.show_course, style=Pack(flex=1)),
                toga.Button("Progresso", on_press=self.show_progress, style=Pack(flex=1, margin_left=6)),
                toga.Button("Analisar", on_press=self.show_analyzer, style=Pack(flex=1, margin_left=6)),
                toga.Button("Dados", on_press=self.show_data, style=Pack(flex=1, margin_left=6)),
            ])
            support_toolbar = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("Dicionário", on_press=self.show_glossary, style=Pack(flex=1)),
                toga.Button("Tutor", on_press=self.show_tutor, style=Pack(flex=1, margin_left=6)),
                toga.Button("Projetos", on_press=self.show_projects, style=Pack(flex=1, margin_left=6)),
            ])
            actions = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("← Rever", on_press=lambda _w: self.swipe("again"), style=Pack(flex=1)),
                toga.Button("Praticar", on_press=self.practice, style=Pack(flex=1, margin_left=6)),
                toga.Button("Virar", on_press=self.flip_card, style=Pack(flex=1, margin_left=6)),
                toga.Button("Sei isto →", on_press=lambda _w: self.swipe("known"), style=Pack(flex=1, margin_left=6)),
            ])
            self.cards_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toolbar, learning_toolbar, support_toolbar, self.title_label, self.body_label, actions,
            ])
            self.ide_kind = "card"
            self.prompt = toga.MultilineTextInput(readonly=True, style=Pack(height=190, margin=8))
            self.learning_note = toga.TextInput(
                placeholder="Previsão antes; reflexão depois", style=Pack(margin=8)
            )
            self.editor = toga.MultilineTextInput(style=Pack(flex=1, margin=8))
            code_row = toga.Box(style=Pack(direction=ROW, margin=6))
            for token in ("(", ")", "[", "]", "{", "}", ":", "_", "=", "    "):
                code_row.add(toga.Button(token, on_press=lambda _w, value=token: self.insert_token(value), style=Pack(flex=1)))
            self.output = toga.MultilineTextInput(readonly=True, style=Pack(height=100, margin=8))
            self.ide_mode = toga.Selection(items=["Treino", "Avaliação"], style=Pack(flex=1))
            ide_actions = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("Voltar", on_press=self.back_from_ide, style=Pack(flex=1)),
                self.ide_mode,
                toga.Button("Executar e corrigir", on_press=self.run_code, style=Pack(flex=2, margin_left=6)),
                toga.Button("Seguinte", on_press=self.next_course_unit, style=Pack(flex=1, margin_left=6)),
            ])
            self.ide_box = toga.Box(style=Pack(direction=COLUMN), children=[
                self.prompt, self.learning_note, self.editor, code_row, ide_actions, self.output,
            ])
            self.search_query = toga.TextInput(placeholder="Tema, método, autor ou aplicação", style=Pack(flex=1))
            self.search_area = toga.Selection(items=["Toda a árvore", *self.area_labels], style=Pack(flex=1, margin_left=6))
            search_controls = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("‹ Cards", on_press=self.back, style=Pack(margin_right=6)),
                self.search_query, self.search_area,
                toga.Button("Pesquisar", on_press=self.do_search, style=Pack(margin_left=6)),
            ])
            self.search_results = toga.Selection(items=[], on_change=self.open_search_result, style=Pack(margin=8))
            self.search_preview = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            self.search_box = toga.Box(style=Pack(direction=COLUMN), children=[search_controls, self.search_results, self.search_preview])
            self.reader_title = toga.Label("", style=Pack(font_size=22, font_weight="bold", margin=8))
            self.reader_content = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            reader_controls = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("‹ Pesquisa", on_press=self.show_search, style=Pack(flex=1)),
                toga.Button("Resumo", on_press=lambda _w: self.reader_mode("summary"), style=Pack(flex=1)),
                toga.Button("Simples", on_press=lambda _w: self.reader_mode("simplified"), style=Pack(flex=1)),
                toga.Button("Normal", on_press=lambda _w: self.reader_mode("body"), style=Pack(flex=1)),
            ])
            self.reader_box = toga.Box(style=Pack(direction=COLUMN), children=[reader_controls, self.reader_title, self.reader_content])
            self.game_kind = toga.Selection(items=["Sudoku", "Minesweeper"], style=Pack(flex=1))
            self.game_level = toga.Selection(items=list(DIFFICULTIES), style=Pack(flex=1, margin_left=6))
            self.game_status = toga.Label("Intervalo sem animações", style=Pack(margin=8))
            self.game_grid = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=4))
            game_controls = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("‹ Cards", on_press=self.back), self.game_kind, self.game_level,
                toga.Button("Novo", on_press=self.new_game, style=Pack(margin_left=6)),
                toga.Button("Marcar/Revelar", on_press=self.toggle_game_mode, style=Pack(margin_left=6)),
            ])
            game_session_controls = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("Retomar", on_press=self.resume_game, style=Pack(flex=1)),
                toga.Button("Diário", on_press=self.daily_game, style=Pack(flex=1, margin_left=6)),
                toga.Button("Estatísticas", on_press=self.game_statistics, style=Pack(flex=1, margin_left=6)),
            ])
            keypad = toga.Box(style=Pack(direction=ROW, margin=4))
            for value in range(1, 10):
                keypad.add(toga.Button(str(value), on_press=lambda _w, number=value: self.game_number(number), style=Pack(flex=1)))
            self.games_box = toga.Box(style=Pack(direction=COLUMN), children=[
                game_controls, game_session_controls, self.game_status,
                toga.ScrollContainer(content=self.game_grid, style=Pack(flex=1)), keypad,
            ])
            courses = self.runtime.courses()
            self.course_slugs = {str(item["title"]): str(item["slug"]) for item in courses}
            self.course_select = toga.Selection(
                items=list(self.course_slugs), on_change=self.change_course, style=Pack(flex=1)
            )
            self.unit_select = toga.Selection(items=[], on_change=self.change_unit, style=Pack(flex=1, margin_left=6))
            self.unit_body = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            self.course_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("‹ Cards", on_press=self.back), self.course_select, self.unit_select,
                    toga.Button("Abrir no IDE", on_press=self.open_course_unit, style=Pack(margin_left=6)),
                ]), self.unit_body,
            ])
            self.progress_body = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=12))
            self.progress_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("‹ Cards", on_press=self.back),
                    toga.Label("Progresso local", style=Pack(font_size=24, font_weight="bold", margin_left=10)),
                ]), self.progress_body,
            ])
            self.snippet_input = toga.MultilineTextInput(
                placeholder="Cola código ou pseudocódigo", style=Pack(flex=1, margin=8)
            )
            self.snippet_action = toga.Selection(
                items=["Explicar", "Converter Python", "Problemas", "Testes"], style=Pack(flex=1)
            )
            self.snippet_output = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            self.analyzer_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("‹ Cards", on_press=self.back), self.snippet_action,
                    toga.Button("Abrir imagem…", on_press=self.open_snippet_image, style=Pack(margin_left=6)),
                    toga.Button("Analisar", on_press=self.analyze_snippet, style=Pack(margin_left=6)),
                ]), self.snippet_input, self.snippet_output,
            ])
            self.profile_passphrase = toga.PasswordInput(
                placeholder="Frase-passe (mínimo 10 caracteres)", style=Pack(margin=8)
            )
            self.data_status = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            self.data_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("‹ Cards", on_press=self.back),
                    toga.Label("Perfil portátil cifrado", style=Pack(font_size=22, font_weight="bold", margin_left=10)),
                ]), self.profile_passphrase,
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("Exportar…", on_press=self.export_profile, style=Pack(flex=1)),
                    toga.Button("Antever…", on_press=self.preview_profile, style=Pack(flex=1, margin_left=6)),
                    toga.Button("Importar…", on_press=self.import_profile, style=Pack(flex=1, margin_left=6)),
                ]), self.data_status,
            ])
            self.glossary_query = toga.TextInput(
                placeholder="Função, erro ou conceito", on_change=self.search_glossary,
                style=Pack(flex=1),
            )
            self.glossary_output = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            self.glossary_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("‹ Cards", on_press=self.back), self.glossary_query,
                    toga.Button("Procurar", on_press=self.search_glossary, style=Pack(margin_left=6)),
                ]), self.glossary_output,
            ])
            self.tutor_strategy = toga.Selection(
                items=["Explicar", "Pergunta socrática", "Simplificar"], style=Pack(flex=1)
            )
            self.tutor_question = toga.MultilineTextInput(
                placeholder="Pergunta sobre o conteúdo local", style=Pack(height=130, margin=8)
            )
            self.tutor_output = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            self.tutor_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("‹ Cards", on_press=self.back), self.tutor_strategy,
                    toga.Button("Pedir orientação", on_press=self.ask_tutor, style=Pack(margin_left=6)),
                ]), self.tutor_question, self.tutor_output,
            ])
            self.project_select = toga.Selection(items=[], on_change=self.load_project, style=Pack(flex=1))
            self.project_name = toga.TextInput(placeholder="Nome do projeto", style=Pack(flex=1))
            self.project_path = toga.TextInput(placeholder="main.py", value="main.py", style=Pack(flex=1))
            self.project_editor = toga.MultilineTextInput(style=Pack(flex=1, margin=8))
            self.project_status = toga.Label("Projetos cifrados neste dispositivo.", style=Pack(margin=8))
            self.project_box = toga.Box(style=Pack(direction=COLUMN), children=[
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    toga.Button("‹ Cards", on_press=self.back), self.project_select,
                    toga.Button("Novo", on_press=self.new_project, style=Pack(margin_left=6)),
                ]),
                toga.Box(style=Pack(direction=ROW, margin=8), children=[
                    self.project_name, self.project_path,
                    toga.Button("Guardar", on_press=self.save_project, style=Pack(margin_left=6)),
                ]), self.project_editor, self.project_status,
            ])
            self.main_window = toga.MainWindow(title=self.formal_name)
            self.main_window.content = self.cards_box
            self.render(); self.toggle_contrast(None, initialise=True); self.main_window.show()

        def current(self):
            return self.cards[self.index % len(self.cards)] if self.cards else None
        def render(self):
            item = self.current()
            self.title_label.text = str(item["title"]) if item else "Sem cards"
            self.body_label.value = str(item["body"]) if item else "Altera os filtros."
        def swipe(self, action):
            item = self.current()
            if item: self.runtime.review_card(str(item["id"]), action)
            self.index += 1; self.render()
        def change_mode(self, _widget):
            area_id = self.area_labels.get(str(self.area.value))
            self.cards = self.runtime.cards(
                "recommended" if self.mode.value == "Recomendado" else "free",
                area_id=area_id,
            )
            self.index = 0; self.render()
        def practice(self, _widget):
            item = self.current()
            if not item: return
            if not item.get("exercise_id"):
                self.open_reader(str(item["id"])); return
            self.ide_kind = "card"
            self.prompt.value = str(item["prompt"])
            self.learning_note.value = ""
            self.editor.value = str(item["starter_code"]); self.main_window.content = self.ide_box
        def flip_card(self, _widget):
            item = self.current()
            if not item: return
            sources = self.runtime.sources(str(item["area_id"]))
            self.body_label.value = "Referências\n\n" + "\n".join(
                f"{source['title']}\n{source['canonical_url']}" for source in sources
            ) if sources else "Sem referências para este tema."
        def insert_token(self, token):
            self.editor.value = (self.editor.value or "") + token + (" " if token in {"def", "class"} else "")
        def run_code(self, _widget):
            if self.ide_kind == "course":
                unit = self.current_course_unit
                session = unit["session"]
                if not session["prediction"] and (self.learning_note.value or "").strip():
                    unit["session"] = self.runtime.update_learning_note(
                        str(unit["slug"]), prediction=(self.learning_note.value or "").strip()
                    )
                receipt = self.runtime.execute_course_unit(
                    str(unit["slug"]), self.editor.value or "",
                    mode="evaluation" if self.ide_mode.value == "Avaliação" else "training",
                )
                unit["session"] = receipt["session"]
                actions = "\n".join(f"- {value}" for value in receipt["actions"])
                self.output.value = (
                    ("Código aceite\n" if receipt["passed"] else "Revê o código\n")
                    + f"Tentativa {receipt['attempt_number']} · {receipt['assistance_stage']}\n"
                    + str(receipt["diagnosis"]) + "\n" + actions
                )
                if receipt["passed"]:
                    self.learning_note.value = ""
                    self.learning_note.placeholder = "Reflexão: o que corrigiste?"
                return
            item = self.current()
            result, passed = self.runtime.execute(
                str(item["exercise_id"]), self.editor.value or "",
                str(item["expected_output"]),
            )
            self.output.value = ("Código aceite\n" if passed else "Revê o código\n") + (result.stdout or result.error_message or "Sem output")
            if passed: self.body_label.value = str(item["body"]) + "\n\n" + str(item["code"])
        def back(self, _widget): self.main_window.content = self.cards_box
        def back_from_ide(self, _widget):
            self.main_window.content = self.course_box if self.ide_kind == "course" else self.cards_box
        def show_course(self, _widget):
            self.main_window.content = self.course_box
            self.change_course(None)
        def change_course(self, _widget):
            slug = self.course_slugs.get(str(self.course_select.value))
            self.course_units = self.runtime.course_units(slug or "")
            self.unit_labels = {str(item["title"]): item for item in self.course_units}
            self.unit_select.items = list(self.unit_labels)
            self.change_unit(None)
        def change_unit(self, _widget):
            item = self.unit_labels.get(str(self.unit_select.value)) if hasattr(self, "unit_labels") else None
            self.unit_body.value = (
                f"{item['objective']}\n\n{item['explanation']}\n\nCódigo inicial\n{item['starter_code']}"
                if item else "Escolhe uma unidade."
            )
        def open_course_unit(self, _widget):
            item = self.unit_labels.get(str(self.unit_select.value)) if hasattr(self, "unit_labels") else None
            if item:
                self.current_course_unit = self.runtime.prepare_course_unit(str(item["slug"]))
                self.ide_kind = "course"
                self.course_unit_index = next(
                    (index for index, value in enumerate(self.course_units)
                     if value["slug"] == item["slug"]), 0,
                )
                self.prompt.value = self.runtime.course_unit_brief(self.current_course_unit)
                self.editor.value = str(self.current_course_unit["starter_code"])
                session = self.current_course_unit["session"]
                self.learning_note.value = str(session["reflection"] or session["prediction"])
                self.output.value = "Regista uma previsão e completa o contrato."
                self.main_window.content = self.ide_box
        def next_course_unit(self, _widget):
            if self.ide_kind != "course":
                self.main_window.content = self.cards_box
                return
            if ((self.learning_note.value or "").strip()
                    and self.current_course_unit["session"].get("independent_passed")):
                self.runtime.update_learning_note(
                    str(self.current_course_unit["slug"]),
                    reflection=(self.learning_note.value or "").strip(),
                )
            if self.course_unit_index + 1 >= len(self.course_units):
                self.output.value = "Percurso concluído."
                return
            self.course_unit_index += 1
            next_item = self.course_units[self.course_unit_index]
            self.unit_select.value = str(next_item["title"])
            self.open_course_unit(None)
        def show_progress(self, _widget):
            complete = len(self.runtime.state.completed_units())
            total = sum(int(item["unit_count"]) for item in self.runtime.courses())
            evidence = self.runtime.state.learning_session_summary()
            self.progress_body.value = (
                f"Unidades concluídas: {complete}/{total}\n\n"
                f"Exercícios aprovados: {self.runtime.state.passed_attempts()}\n\n"
                f"Autónomos: {evidence['independent_passes']} · "
                f"Transferência: {evidence['transfer_passes']} · "
                f"Em curso: {evidence['in_progress']}\n\n"
                "Os jogos não alteram o progresso pedagógico."
            )
            self.main_window.content = self.progress_box
        def show_glossary(self, _widget):
            self.main_window.content = self.glossary_box
            self.search_glossary(None)
        def search_glossary(self, _widget):
            entries = self.runtime.glossary(self.glossary_query.value or "")
            self.glossary_output.value = "\n\n".join(
                f"{item['term']}  {item['signature']}\n{item['definition']}"
                for item in entries
            ) or "Nenhuma entrada local encontrada."
        def show_tutor(self, _widget): self.main_window.content = self.tutor_box
        def ask_tutor(self, _widget):
            strategies = {
                "Explicar": "explain", "Pergunta socrática": "socratic", "Simplificar": "simplify",
            }
            try:
                response = self.runtime.ask_tutor(
                    self.tutor_question.value or "",
                    strategy=strategies.get(str(self.tutor_strategy.value), "explain"),
                )
                body = str(response["answer"])
                evidence = response.get("evidence", ())
                if evidence:
                    body += "\n\nEvidência local\n" + "\n".join(
                        f"• {item['title']}" for item in evidence
                    )
                self.tutor_output.value = body + f"\n\nConfiança: {float(response['confidence']):.0%}"
            except Exception as exc:
                self.tutor_output.value = f"Tutor indisponível: {exc}"
        def show_projects(self, _widget):
            self.main_window.content = self.project_box
            self.refresh_projects()
        def refresh_projects(self):
            self.project_items = {
                f"{item['name']} · {item['relative_path']}": item
                for item in self.runtime.projects()
            }
            self.project_select.items = list(self.project_items)
        def load_project(self, _widget):
            item = getattr(self, "project_items", {}).get(str(self.project_select.value))
            if not item: return
            self.project_id = str(item["id"])
            self.project_name.value = str(item["name"])
            self.project_path.value = str(item["relative_path"])
            self.project_editor.value = str(item["source"])
            self.project_status.text = "Projeto aberto apenas do armazenamento local cifrado."
        def new_project(self, _widget):
            self.project_id = None
            self.project_select.value = None
            self.project_name.value = ""
            self.project_path.value = "main.py"
            self.project_editor.value = ""
            self.project_status.text = "Novo projeto local."
        def save_project(self, _widget):
            try:
                item = self.runtime.save_project(
                    self.project_name.value or "Projeto sem nome",
                    self.project_editor.value or "",
                    project_id=getattr(self, "project_id", None),
                    relative_path=self.project_path.value or "main.py",
                )
                self.project_id = str(item["id"])
                self.project_status.text = "Projeto cifrado e guardado."
                self.refresh_projects()
            except Exception as exc:
                self.project_status.text = str(exc)
        def show_analyzer(self, _widget): self.main_window.content = self.analyzer_box
        def analyze_snippet(self, _widget):
            from aprendix_mobile.contracts import SnippetAction, SnippetRequestDTO
            actions = {"Explicar": SnippetAction.EXPLAIN, "Converter Python": SnippetAction.TO_PYTHON,
                       "Problemas": SnippetAction.FIND_PROBLEMS, "Testes": SnippetAction.CREATE_TESTS}
            try:
                result = self.runtime.analyze_snippet(SnippetRequestDTO(
                    text=self.snippet_input.value or "", action=actions[str(self.snippet_action.value or "Explicar")]
                ))
                body = result.summary + "\n\n" + "\n".join(result.line_explanations)
                if result.problems: body += "\n\nProblemas\n• " + "\n• ".join(result.problems)
                if result.suggested_tests: body += "\n\nTestes\n• " + "\n• ".join(result.suggested_tests)
                if result.proposed_code: body += "\n\nPython proposto (não executado)\n" + result.proposed_code
                self.snippet_output.value = body
            except Exception as exc: self.snippet_output.value = str(exc)
        async def open_snippet_image(self, _widget):
            try:
                selected = await self.main_window.dialog(toga.OpenFileDialog(
                    "Escolher imagem", file_types=["png", "jpg", "jpeg"]
                ))
                if selected:
                    draft = self.runtime.extract_image(Path(selected))
                    self.snippet_input.value = draft.text
                    self.snippet_output.value = f"OCR {draft.confidence:.0%}; confirma o texto antes de analisar."
            except Exception as exc: self.snippet_output.value = str(exc)
        def show_data(self, _widget): self.main_window.content = self.data_box
        def _profile_secret(self):
            secret = self.profile_passphrase.value or ""
            if len(secret) < 10:
                raise ValueError("A frase-passe precisa de pelo menos 10 caracteres.")
            return secret
        async def export_profile(self, _widget):
            try:
                selected = await self.main_window.dialog(toga.SaveFileDialog(
                    "Exportar perfil", suggested_filename="Aprendix-perfil.apxprofile",
                    file_types=["apxprofile"],
                ))
                if selected:
                    self.runtime.export_profile(Path(selected), self._profile_secret())
                    self.data_status.value = "Perfil exportado e cifrado."
            except Exception as exc: self.data_status.value = str(exc)
        async def preview_profile(self, _widget): await self._open_profile(False)
        async def import_profile(self, _widget): await self._open_profile(True)
        async def _open_profile(self, commit):
            try:
                selected = await self.main_window.dialog(toga.OpenFileDialog(
                    "Escolher perfil", file_types=["apxprofile"]
                ))
                if selected:
                    operation = self.runtime.import_profile if commit else self.runtime.preview_profile
                    result = operation(Path(selected), self._profile_secret())
                    self.data_status.value = ("Importado: " if commit else "Antevisão: ") + str(result)
            except Exception as exc: self.data_status.value = str(exc)
        def show_search(self, _widget): self.main_window.content = self.search_box
        def do_search(self, _widget):
            self.search_hits = self.runtime.search(
                self.search_query.value or "",
                area_id=self.area_labels.get(str(self.search_area.value)),
            )
            self.search_labels = {f"{item['title']} · {item['score']:.0%}": str(item["id"]) for item in self.search_hits}
            self.search_results.items = list(self.search_labels)
            self.search_preview.value = "\n\n".join(
                f"{item['title']}\n{item['excerpt']}" for item in self.search_hits[:8]
            ) or "Sem resultados neste ramo."
        def open_search_result(self, _widget):
            item_id = getattr(self, "search_labels", {}).get(str(self.search_results.value))
            if item_id: self.open_reader(item_id)
        def open_reader(self, item_id):
            self.reader_detail = self.runtime.reading(item_id, self.search_query.value or "")
            self.reader_title.text = str(self.reader_detail["title"])
            self.reader_mode("summary"); self.main_window.content = self.reader_box
        def reader_mode(self, mode):
            if not getattr(self, "reader_detail", None): return
            body = str(self.reader_detail[mode])
            concepts = self.reader_detail.get("concepts", ())
            if concepts:
                body += "\n\nTutor de conceitos\n" + "\n\n".join(
                    f"{item['term']} · {item['signature']}\n{item['definition']}" for item in concepts
                )
            self.reader_content.value = body
        def show_games(self, _widget):
            self.main_window.content = self.games_box
            self.new_game(None)
        def new_game(self, _widget):
            kind = str(self.game_kind.value or "Sudoku")
            level = str(self.game_level.value or DIFFICULTIES[0])
            self.game_session = self.runtime.games.new(
                "sudoku" if kind == "Sudoku" else "minesweeper", level
            )
            self.game = self.game_session.game; self._game_started = time.monotonic()
            self.game_selected, self.game_flag_mode = None, False
            self.game_status.text = f"{kind} · {level} · sem animações"
            self.draw_game()
        def daily_game(self, _widget):
            kind = str(self.game_kind.value or "Sudoku")
            level = str(self.game_level.value or DIFFICULTIES[0])
            self.game_session = self.runtime.games.new(
                "sudoku" if kind == "Sudoku" else "minesweeper", level, daily=True
            )
            self.game = self.game_session.game; self._game_started = time.monotonic()
            self.game_selected, self.game_flag_mode = None, False
            self.game_status.text = "Desafio diário local · sem recompensa pedagógica"
            self.draw_game()
        def resume_game(self, _widget):
            kind = str(self.game_kind.value or "Sudoku")
            level = str(self.game_level.value or DIFFICULTIES[0])
            session = self.runtime.games.resume(
                "sudoku" if kind == "Sudoku" else "minesweeper", level
            )
            if session is None:
                self.game_status.text = "Não existe jogo guardado nesta dificuldade."
                return
            self.game_session, self.game = session, session.game
            self._game_started = time.monotonic(); self.draw_game()
            self.game_status.text = "Jogo retomado do armazenamento local cifrado."
        def game_statistics(self, _widget):
            rows = self.runtime.games.statistics()
            self.game_status.text = " · ".join(
                f"{item['game']} {item['wins']}/{item['plays']}" for item in rows
            ) or "Ainda não existem jogos terminados."
        def save_game(self):
            if not hasattr(self, "game_session"): return
            now = time.monotonic()
            self.game_session.elapsed_seconds += max(0, int(now - self._game_started))
            self._game_started = now
            self.runtime.games.save(self.game_session)
        def draw_game(self):
            self.game_grid.clear()
            rows, cols = (9, 9) if isinstance(self.game, SudokuGame) else (self.game.rows, self.game.cols)
            for row in range(rows):
                line = toga.Box(style=Pack(direction=ROW))
                for col in range(cols):
                    if isinstance(self.game, SudokuGame):
                        value = self.game.board[row][col]; title = str(value) if value else " "
                        callback = lambda _w, r=row, c=col: self.pick_game(r, c)
                    else:
                        cell = (row, col); title = "⚑" if cell in self.game.flagged else " "
                        if cell in self.game.revealed:
                            count = self.game.count(row, col)
                            title = "✹" if cell in self.game.mines else (str(count) if count else "·")
                        callback = lambda _w, r=row, c=col: self.play_mine(r, c)
                    line.add(toga.Button(title, on_press=callback, style=Pack(flex=1)))
                self.game_grid.add(line)
        def pick_game(self, row, col):
            if (row, col) not in self.game.fixed: self.game_selected = (row, col)
        def game_number(self, number):
            if isinstance(self.game, SudokuGame) and self.game_selected:
                self.game.set(*self.game_selected, number); self.draw_game(); self.save_game()
                if self.game.won:
                    self.runtime.games.finish(self.game_session)
                    self.game_status.text = "Sudoku concluído."
        def play_mine(self, row, col):
            self.game.toggle_flag(row, col) if self.game_flag_mode else self.game.reveal(row, col)
            self.draw_game(); self.save_game()
            if self.game.lost: self.game_status.text = "Encontraste uma mina."
            elif self.game.won: self.game_status.text = "Minesweeper concluído."
            if self.game.lost or self.game.won:
                self.runtime.games.finish(self.game_session)
        def toggle_game_mode(self, _widget):
            self.game_flag_mode = not getattr(self, "game_flag_mode", False)
        def toggle_contrast(self, _widget, initialise=False):
            # Native controls retain system Dynamic Type and VoiceOver semantics.
            if not initialise:
                self.theme = "light" if self.theme == "dark" else "dark"
                self.runtime.state.set_setting("theme", self.theme)
            colour = "#07101F" if self.theme == "dark" else "#F3F6FA"
            self.cards_box.style.background_color = colour
            self.ide_box.style.background_color = colour
            self.search_box.style.background_color = colour
            self.reader_box.style.background_color = colour
            self.course_box.style.background_color = colour
            self.progress_box.style.background_color = colour
            self.analyzer_box.style.background_color = colour
            self.data_box.style.background_color = colour
            self.glossary_box.style.background_color = colour
            self.tutor_box.style.background_color = colour
            self.project_box.style.background_color = colour

    return AprendixIOS("Aprendix", "io.aprendix.mobile")
