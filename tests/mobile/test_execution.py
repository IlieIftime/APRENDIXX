from aprendix_mobile.execution import ExecutionLimits, RestrictedPython


def test_functions_loops_collections_and_output() -> None:
    result = RestrictedPython().run("""
def pares(valores):
    saida = []
    for valor in valores:
        if valor % 2 == 0:
            saida.append(valor)
    return saida
print(pares([1, 2, 3, 4]))
""")
    assert result.status == "ok"
    assert result.stdout == "[2, 4]\n"


def test_classes_are_interpreted_without_host_exec() -> None:
    result = RestrictedPython().run("""
class Conta:
    def __init__(self, saldo):
        self.saldo = saldo
    def depositar(self, valor):
        self.saldo += valor
c = Conta(10)
c.depositar(5)
print(c.saldo)
""")
    assert result.status == "ok"
    assert result.stdout == "15\n"


def test_host_capabilities_and_introspection_are_rejected() -> None:
    for source in (
        "import os", "open('x')", "().__class__", "eval('1+1')",
        "class X(object):\n    pass", "[x for x in range(3)]",
    ):
        result = RestrictedPython().run(source)
        assert result.status in {"rejected", "runtime_error"}
        assert not result.stdout


def test_instruction_output_and_value_budgets_stop_abuse() -> None:
    interpreter = RestrictedPython(ExecutionLimits(
        timeout_ms=500, max_steps=100, max_output_bytes=20,
        max_collection_items=20, max_integer_bits=128,
    ))
    assert interpreter.run("while True:\n    pass").status == "limit"
    assert interpreter.run("print('x' * 100)").status == "limit"
    assert interpreter.run("print(2 ** 10000)").status == "limit"
    assert interpreter.run("print(list(range(100)))").status == "limit"


def test_syntax_and_runtime_errors_are_bounded_results() -> None:
    assert RestrictedPython().run("if").status == "syntax_error"
    result = RestrictedPython().run("print(1 / 0)")
    assert result.status == "runtime_error"
    assert result.error_type == "ZeroDivisionError"
