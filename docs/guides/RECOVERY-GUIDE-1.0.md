# Recuperação do Aprendix 1.0

1. Fecha o Aprendix. Não apagues `%LOCALAPPDATA%\Aprendix`.
2. Executa `py scripts\backup_profile.py --label antes-da-recuperacao` para criar uma cópia consistente. Guarda a pasta num volume cifrado: contém a base de dados e a respetiva chave.
3. Executa `Desinstalar-Aprendix.bat`. Por defeito remove executáveis e venvs, preservando o perfil.
4. Executa `Instalar-Aprendix.bat`. O instalador cria uma venv isolada, recompila, instala e executa o self-test antes de criar o atalho.
5. Se a base estiver corrompida, fecha a app e repõe `aprendix.db` e `fields.key` do mesmo backup. Nunca mistures a base de um backup com a chave de outro.
6. Para conteúdo, escolhe uma versão anterior assinada no gestor de packs; a ativação é atómica e não altera o perfil.

O desinstalador só apaga dados do utilizador quando recebe explicitamente `-RemoveUserData`. Essa operação é destrutiva e não deve ser usada numa recuperação normal.
