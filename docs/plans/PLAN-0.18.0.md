# Plano de correção e integração 0.18.0

Estado: executado pela ordem abaixo. Os jogos foram integrados apenas após a validação do núcleo pedagógico.

1. Integridade e proveniência: detetar fronteiras de publicações anexadas em PDFs, manter os dados cifrados e retirar excertos em quarentena da pesquisa, dos cards, dos clusters e da bibliografia.
2. Cards: substituir parágrafos crus de PDFs por factos originais “Sabias que?”, classificar pelo conteúdo, ligar à árvore temática, feedback A1, repetição espaçada, filtros, setas, swipe, verso e fontes navegáveis.
3. Dicionário: ampliar palavras da linguagem, funções, bibliotecas, algoritmos, matemática e IA; ranking top-k tolerante; pesquisa web segura apenas quando falta uma entrada exata; degradação offline explícita.
4. Pesquisa e leitor: filtros e atalhos hierárquicos, resumo do resultado aberto, versão matemática acessível, conteúdo normal selecionável, tutor apenas por duplo clique/toque, bibliografia navegável e abertura real de URLs/ficheiros locais.
5. IDE, testes e progresso: limpar enunciados legados, tornar texto/código/output copiáveis, redimensionar enunciado, diagnóstico AST local, sandbox, avanço automático, cronómetro prático, testes teóricos em treino ou avaliação temporizada e plano de estudo configurável.
6. Navegação e visual: scroll por conteúdo e barra visível, tema claro/escuro, grafo com zoom/drag/click e uma espinha de pré-requisitos, correção de escala DPI no Windows.
7. Validação pedagógica: testes unitários/integração, migração sobre a biblioteca real, self-test do sandbox/SQLite e smoke visual da janela.
8. Games: só então, aba isolada com Sudoku e Minesweeper sem animações e com três dificuldades no desktop e Android.
9. Release: atualizar seed mobile, documentação, versão, EXE/instalador Windows e APK sideload Android; validar hashes, assinatura e metadados.

## Critérios essenciais

- Nenhum conteúdo em quarentena pode participar na recuperação ou recomendação.
- Os cards apresentados pela UI são texto original Aprendix e não cópias de livros.
- O código do utilizador continua sem rede e executado no helper isolado.
- Falhas de Internet não bloqueiam dicionário, curso, IDE, cards ou jogos.
- Android continua local-first; URLs bibliográficas são abertas pela aplicação externa escolhida pelo sistema.
