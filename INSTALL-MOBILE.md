# Instalação móvel do Aprendix 1.0.0

O Android e o iOS usam formatos e regras de assinatura diferentes. Um APK só
funciona em Android; não pode ser instalado num iPhone ou iPad.

## Android — instalação direta do APK

### Requisitos

- Android 8.0/API 26 ou superior.
- Dispositivo com CPU `arm64-v8a`.
- Cerca de 100 MB livres para o pacote, extração e dados locais.

O APK já inclui Python, Kivy, bibliotecas nativas e a base de conhecimento lite.
Não é necessário instalar Python, criar uma venv ou manter ligação à Internet.

Ficheiro:

`dist/mobile/Aprendix-1.0.0-android-arm64-release.apk`

SHA-256:

`9C1869F0271DC1622CB3A2B26C262CCF772988F80CD28E2B8059CC8918FF0F3F`

### Método A — pelo gestor de ficheiros

1. Copia o APK para o dispositivo por USB, cartão, Bluetooth ou armazenamento local.
2. No Android, abre o APK no gestor de ficheiros.
3. Quando solicitado, permite a esse gestor de ficheiros **Instalar aplicações desconhecidas**.
4. Confirma **Instalar**.
5. No fim escolhe **Abrir**. Por segurança, o Android não permite que um APK se execute silenciosamente logo após a instalação.
6. Na primeira abertura, aceita notificações se quiseres lembretes de revisão espaçada.
7. Podes voltar a desativar a autorização de “aplicações desconhecidas” para o gestor de ficheiros.

A aplicação não pede a permissão `INTERNET`. Progresso, respostas, chave e base do
utilizador ficam na área privada da aplicação.

### Método B — instalação e arranque automáticos por USB

1. Instala o Android SDK Platform Tools oficial no Windows.
2. No Android ativa **Opções de programador** e **Depuração USB**.
3. Liga o dispositivo e aceita a impressão digital RSA apresentada.
4. Faz duplo clique em `Instalar-Android-ADB.bat`.

O BAT executa `adb install -r` e abre a atividade principal após uma instalação
bem-sucedida. Não foi possível ensaiar esta etapa num dispositivo físico durante a
release porque nenhum estava ligado; o próprio BAT valida a ligação antes de alterar o
dispositivo.

### Atualizações e assinatura

Este artefacto é um APK release não-debuggable, assinado com uma identidade local
persistente guardada fora do repositório. Não é uma release de loja. Android
só permite atualizar uma aplicação quando o novo APK tem o mesmo package ID e a mesma
chave. Conserva a instalação atual e usa APKs produzidos com a mesma chave; caso a chave
mude, será necessário desinstalar primeiro, perdendo os dados locais não exportados.
A identidade encontra-se no ambiente WSL em `~/.config/aprendix/signing`; guarda uma
cópia privada desse diretório e nunca o distribuas juntamente com o APK.

## iOS/iPadOS — compilação e instalação fora da App Store

O projeto iOS está preparado, mas a Apple exige que cada aplicação seja compilada e
assinada num Mac. Briefcase só suporta a geração do projeto iOS em macOS e produz um
projeto Xcode, não uma imagem de instalador universal.

### Requisitos no Mac

- macOS com Xcode e Command Line Tools.
- Python 3.11 ou superior.
- Apple Account adicionada em **Xcode > Settings > Accounts**.
- Cabo USB ou emparelhamento do iPhone/iPad com o Mac.
- Código completo desta pasta do projeto.

### Construir o projeto

No Terminal, na raiz do projeto:

```bash
chmod +x mobile/scripts/build_ios.sh
bash mobile/scripts/build_ios.sh
```

O script cria uma venv própria `.venv-aprendix-ios`, instala dependências, corre os
testes móveis, cria o projeto Briefcase, integra o bridge nativo de Keychain,
notificações e haptics, e compila-o. O projeto Xcode fica sob
`build/aprendix/iOS/`.

### Instalar diretamente num iPhone/iPad com Xcode

1. Abre o `.xcodeproj` criado em `build/aprendix/iOS/`.
2. Seleciona o target **Aprendix** e abre **Signing & Capabilities**.
3. Ativa **Automatically manage signing** e escolhe a tua Team/Apple Account.
4. Liga e desbloqueia o dispositivo, confirma **Confiar neste computador** e ativa Developer Mode se o iOS o pedir.
5. Seleciona o dispositivo como run destination.
6. Escolhe **Product > Run**. O Xcode cria o provisioning profile, instala e abre a aplicação.

Uma Apple Account gratuita pode usar uma Personal Team, mas os perfis de instalação
expiram após sete dias e a app tem de ser novamente assinada/instalada. Para distribuir
a vários dispositivos registados sem a App Store é necessário o Apple Developer Program,
um certificado de distribuição e um perfil Ad Hoc com os UDID desses dispositivos.

### Exportar um IPA Ad Hoc

1. Regista os dispositivos na conta Apple Developer.
2. Cria/seleciona um App ID, certificado de distribuição e provisioning profile Ad Hoc.
3. No Xcode seleciona um destino físico/genérico e usa **Product > Archive**.
4. No Organizer escolhe **Distribute App**, a opção para dispositivos registados/Ad Hoc e exporta o IPA.
5. Instala o IPA apenas nos dispositivos incluídos no perfil, através de Xcode ou Apple Configurator.

Não existe um IPA universal que possa ser instalado em qualquer iPhone sem assinatura,
provisioning ou uma via de distribuição autorizada pela Apple.

## Documentação oficial

- Briefcase iOS: https://briefcase.beeware.org/en/latest/reference/platforms/iOS/xcode/
- Executar em dispositivo com Xcode: https://developer.apple.com/documentation/Xcode/running-your-app-on-simulated-or-physical-devices
- Distribuição para dispositivos registados: https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices
- Contas e limites de Personal Team: https://developer.apple.com/help/account/basics/about-your-developer-account
- Buildozer/Android: https://buildozer.readthedocs.io/en/stable/
