"""Curated knowledge map and deterministic pedagogical reading assistance.

The catalogue stores bibliographic metadata and Aprendix-authored overviews. It
never mirrors protected book or article text. Full text is exposed only when it
was explicitly ingested from a local file by the user.
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class AreaDefinition:
    id: str
    parent_id: str | None
    title: str
    description: str
    position: int
    icon: str
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    id: str
    area_ids: tuple[str, ...]
    title: str
    authors: tuple[str, ...]
    year: int | None
    source_type: str
    url: str
    doi: str | None
    overview: str
    why: str
    access_note: str = "Consultar a fonte oficial; o Aprendix guarda apenas metadados e síntese original."
    license_note: str = "Direitos pertencem aos respetivos autores/editora; não é armazenada uma cópia integral."
    provenance: str = "curated-primary-source-2026-08"


AREAS: tuple[AreaDefinition, ...] = (
    AreaDefinition("programming", None, "Programação e Computação", "Base sólida para construir, analisar e manter software.", 0, "</>"),
    AreaDefinition("prog-foundations", "programming", "Fundamentos", "Pensamento computacional, tipos, controlo de fluxo, funções e depuração.", 0, "01", ("programming", "variavel", "function", "debug")),
    AreaDefinition("python", "programming", "Python", "Python idiomático, biblioteca padrão, testes e ferramentas.", 1, "Py", ("python", "pytest", "decorator", "iterator", "asyncio")),
    AreaDefinition("oop", "programming", "Programação orientada a objetos", "Estado, comportamento, encapsulamento, composição e padrões.", 2, "OO", ("object oriented", "class", "inheritance", "polymorphism", "encapsulation")),
    AreaDefinition("data-structures", "programming", "Estruturas de dados", "Arrays, listas, pilhas, filas, árvores, heaps, tabelas de dispersão e grafos.", 3, "DS", ("data structure", "linked list", "stack", "queue", "heap", "hash table", "tree", "graph")),
    AreaDefinition("classic-algorithms", "programming", "Algoritmos clássicos", "Ordenação, pesquisa, recursão, programação dinâmica e algoritmos em grafos.", 4, "ALG", ("algorithm", "sorting", "binary search", "dynamic programming", "dijkstra", "breadth first", "depth first", "complexity")),
    AreaDefinition("software-engineering", "programming", "Engenharia de software", "Arquitetura, APIs, testes, Git, qualidade, DDD e sistemas distribuídos.", 5, "SE", ("software architecture", "testing", "api", "ddd", "git", "distributed system")),
    AreaDefinition("databases", "programming", "Bases de dados", "SQL, NoSQL, modelação, índices, transações e processamento de dados.", 6, "DB", ("sql", "database", "nosql", "mongodb", "postgres", "transaction", "index")),
    AreaDefinition("web", "programming", "Web e aplicações", "HTML, CSS, JavaScript, React e frameworks web Python.", 7, "WEB", ("html", "css", "javascript", "react", "django", "fastapi", "flask", "bootstrap")),
    AreaDefinition("systems", "programming", "Sistemas, redes e DevOps", "Sistemas operativos, concorrência, redes, contentores e entrega contínua.", 8, "SYS", ("operating system", "network", "docker", "devops", "concurrency", "thread")),

    AreaDefinition("math-data", None, "Matemática e Dados", "Ferramentas matemáticas e práticas de dados que sustentam a IA.", 1, "Σ"),
    AreaDefinition("linear-algebra", "math-data", "Álgebra linear", "Vetores, matrizes, espaços, decomposições e geometria de representações.", 0, "LA", ("linear algebra", "matrix", "vector", "eigenvalue", "svd", "tensor")),
    AreaDefinition("calculus", "math-data", "Cálculo", "Derivadas, gradientes, integrais e regra da cadeia.", 1, "∂", ("calculus", "derivative", "gradient", "chain rule", "integral")),
    AreaDefinition("probability", "math-data", "Probabilidade e estatística", "Distribuições, estimação, inferência, incerteza e desenho experimental.", 2, "P", ("probability", "statistics", "bayesian", "distribution", "variance", "hypothesis")),
    AreaDefinition("optimization", "math-data", "Otimização", "Objetivos, restrições, convexidade e métodos baseados em gradiente.", 3, "OPT", ("optimization", "convex", "gradient descent", "objective function", "regularization")),
    AreaDefinition("data-practice", "math-data", "Ciência e engenharia de dados", "Limpeza, exploração, pipelines, visualização e qualidade dos dados.", 4, "DATA", ("pandas", "numpy", "data science", "etl", "visualization", "feature engineering")),

    AreaDefinition("artificial-intelligence", None, "Inteligência Artificial", "Do raciocínio simbólico à aprendizagem moderna e aos agentes.", 2, "AI"),
    AreaDefinition("ai-foundations", "artificial-intelligence", "Fundamentos de IA", "Representação de conhecimento, pesquisa, planeamento e decisão.", 0, "AI", ("artificial intelligence", "knowledge representation", "planning", "search algorithm")),
    AreaDefinition("classical-ml", "artificial-intelligence", "Machine Learning clássico", "Modelos supervisionados, não supervisionados e avaliação rigorosa.", 1, "ML", ("machine learning", "regression", "classification", "svm", "decision tree", "random forest", "k-means", "clustering")),
    AreaDefinition("probabilistic-ml", "classical-ml", "ML probabilístico", "Modelos gráficos, inferência Bayesiana, processos gaussianos e variáveis latentes.", 0, "PML", ("probabilistic model", "bayesian network", "gaussian process", "latent variable", "markov")),
    AreaDefinition("ensemble-learning", "classical-ml", "Ensembles", "Bagging, boosting, random forests e combinação calibrada de modelos.", 1, "ENS", ("ensemble", "boosting", "bagging", "xgboost", "random forest")),
    AreaDefinition("neural-networks", "artificial-intelligence", "Redes neuronais (ANNs)", "Perceptrões multicamada, ativações, backpropagation e representação distribuída.", 2, "ANN", ("neural network", "ann", "perceptron", "backpropagation", "activation function")),
    AreaDefinition("deep-learning", "neural-networks", "Deep Learning", "Treino de redes profundas, normalização, regularização e escalabilidade.", 0, "DL", ("deep learning", "deep neural", "dropout", "batch normalization", "representation learning")),
    AreaDefinition("convolutional-networks", "neural-networks", "CNNs", "Convolução, campos recetivos e arquiteturas residuais.", 1, "CNN", ("convolutional", "cnn", "resnet", "feature map", "kernel")),
    AreaDefinition("sequence-models", "neural-networks", "RNNs e sequências", "Recorrência, LSTM, GRU e dependências temporais.", 2, "RNN", ("recurrent neural", "rnn", "lstm", "gru", "sequence model")),
    AreaDefinition("transformers", "neural-networks", "Transformers e atenção", "Self-attention, embeddings posicionais, pré-treino e adaptação.", 3, "TR", ("transformer", "self-attention", "attention mechanism", "language model", "embedding")),
    AreaDefinition("generative-ai", "neural-networks", "IA generativa", "Autoencoders, GANs, difusão e modelos generativos de linguagem.", 4, "GEN", ("generative", "gan", "diffusion model", "variational autoencoder", "llm")),
    AreaDefinition("computer-vision", "artificial-intelligence", "Visão computacional", "Classificação, deteção, segmentação, tracking e representação visual.", 3, "CV", ("computer vision", "image classification", "object detection", "segmentation", "opencv", "vision transformer")),
    AreaDefinition("natural-language", "artificial-intelligence", "Processamento de linguagem natural", "Texto, tokenização, semântica, tradução e recuperação de informação.", 4, "NLP", ("natural language", "nlp", "tokenization", "translation", "information retrieval", "rag")),
    AreaDefinition("reinforcement-learning", "artificial-intelligence", "Aprendizagem por reforço", "MDPs, valor, políticas, exploração e aprendizagem com feedback.", 5, "RL", ("reinforcement learning", "q-learning", "policy gradient", "reward", "markov decision")),
    AreaDefinition("autonomous-agents", "artificial-intelligence", "Agentes autónomos", "Agentes que planeiam, usam ferramentas, mantêm memória e avaliam ações.", 6, "AG", ("autonomous agent", "ai agent", "agentic", "tool use", "reasoning and acting")),
    AreaDefinition("agent-architectures", "autonomous-agents", "Arquiteturas de agentes", "Ciclos observar-planear-agir, ReAct, reflexão e controlo de execução.", 0, "A1", ("react", "reflexion", "planner", "reasoning trace", "agent architecture")),
    AreaDefinition("agent-memory", "autonomous-agents", "Memória e conhecimento", "Memória episódica, semântica, recuperação e gestão de contexto.", 1, "MEM", ("agent memory", "episodic memory", "semantic memory", "context management")),
    AreaDefinition("multi-agent", "autonomous-agents", "Sistemas multiagente", "Coordenação, comunicação, papéis, consenso e comportamento emergente.", 2, "MAS", ("multi-agent", "agent communication", "coordination", "swarm")),
    AreaDefinition("agent-evaluation", "autonomous-agents", "Avaliação e segurança de agentes", "Métricas, sandboxes, observabilidade, falhas e intervenção humana.", 3, "SAFE", ("agent evaluation", "sandbox", "guardrail", "human in the loop", "agent safety")),
    AreaDefinition("responsible-ai", "artificial-intelligence", "IA responsável e explicável", "Robustez, privacidade, justiça, interpretação e utilização segura.", 7, "RAI", ("responsible ai", "explainable ai", "fairness", "privacy", "robustness", "interpretability")),

    AreaDefinition("applications", None, "Áreas Aplicadas", "Aplicação criteriosa de programação, dados e IA a problemas reais.", 3, "APP"),
    AreaDefinition("finance-app", "applications", "Finanças e risco", "Séries temporais, risco, fraude, otimização e validação sem leakage.", 0, "FIN", ("finance", "portfolio", "risk", "fraud", "trading")),
    AreaDefinition("health-app", "applications", "Saúde e bioinformática", "Dados clínicos, imagem médica, biologia computacional e validação responsável.", 1, "BIO", ("healthcare", "medical", "bioinformatics", "clinical", "genomics")),
    AreaDefinition("robotics-app", "applications", "Robótica e controlo", "Perceção, localização, planeamento, controlo e interação física.", 2, "ROB", ("robotics", "control system", "slam", "motion planning")),
    AreaDefinition("games-app", "applications", "Jogos e simulação", "Motores, IA de jogos, procura, simulação e geração procedural.", 3, "GAME", ("game", "simulation", "pathfinding", "procedural generation")),
    AreaDefinition("recommendation-app", "applications", "Recomendação e personalização", "Ranking, filtragem colaborativa, feedback e avaliação offline/online.", 4, "REC", ("recommender", "recommendation system", "collaborative filtering", "ranking")),
    AreaDefinition("time-series-app", "applications", "Séries temporais", "Previsão, anomalias, sazonalidade e validação temporal.", 5, "TS", ("time series", "forecasting", "seasonality", "anomaly detection")),
    AreaDefinition("cybersecurity-app", "applications", "Cibersegurança", "Deteção, análise de comportamento, segurança de software e modelos adversariais.", 6, "SEC", ("cybersecurity", "malware", "intrusion", "adversarial attack", "secure coding")),
    AreaDefinition("science-app", "applications", "Computação científica", "Modelação, simulação, métodos numéricos e descoberta científica assistida.", 7, "SCI", ("scientific computing", "numerical method", "simulation", "physics", "chemistry")),
    AreaDefinition("edge-mobile-app", "applications", "IA móvel e edge", "Inferência eficiente, quantização, privacidade e limitações do dispositivo.", 8, "EDGE", ("edge ai", "mobile ai", "quantization", "onnx", "tinyml")),
)


PRIMARY_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition("src-clrs", ("classic-algorithms", "data-structures"), "Introduction to Algorithms", ("Thomas H. Cormen", "Charles E. Leiserson", "Ronald L. Rivest", "Clifford Stein"), 2022, "book", "https://mitpress.mit.edu/9780262046305/introduction-to-algorithms/", None, "Referência sistemática para estruturas de dados, análise assintótica e desenho de algoritmos.", "Liga implementações a invariantes, provas de correção e custos de tempo/memória."),
    SourceDefinition("src-esl", ("classical-ml", "probability"), "The Elements of Statistical Learning", ("Trevor Hastie", "Robert Tibshirani", "Jerome Friedman"), 2009, "book", "https://hastie.su.domains/ElemStatLearn/", None, "Tratamento estatístico de regressão, classificação, regularização, kernels, árvores e ensembles.", "Ajuda a compreender pressupostos e trade-offs por trás dos algoritmos clássicos."),
    SourceDefinition("src-probml", ("probabilistic-ml", "classical-ml", "probability"), "Probabilistic Machine Learning: An Introduction", ("Kevin P. Murphy",), 2022, "book", "https://probml.github.io/pml-book/book1.html", None, "Percurso unificado por modelos probabilísticos, decisão Bayesiana e aprendizagem moderna.", "Explicita incerteza, inferência e ligação entre modelos clássicos e deep learning."),
    SourceDefinition("src-dlbook", ("deep-learning", "neural-networks", "generative-ai"), "Deep Learning", ("Ian Goodfellow", "Yoshua Bengio", "Aaron Courville"), 2016, "book", "https://www.deeplearningbook.org/", None, "Base conceptual de redes profundas, otimização, regularização e modelos generativos.", "É uma referência autoral abrangente para entender princípios além de APIs."),
    SourceDefinition("src-rlbook", ("reinforcement-learning",), "Reinforcement Learning: An Introduction", ("Richard S. Sutton", "Andrew G. Barto"), 2018, "book", "https://mitpress.mit.edu/9780262039246/reinforcement-learning/", None, "Introdução estruturada a previsão, controlo, diferenças temporais e aproximação de funções.", "Organiza RL a partir da interação agente-ambiente e do retorno esperado."),
    SourceDefinition("src-aima", ("ai-foundations", "autonomous-agents"), "Artificial Intelligence: A Modern Approach", ("Stuart Russell", "Peter Norvig"), 2021, "book", "https://aima.cs.berkeley.edu/", None, "Mapa amplo de agentes, procura, planeamento, incerteza, aprendizagem e implicações sociais.", "Fornece uma espinha dorsal para ligar IA clássica, aprendizagem e agentes."),
    SourceDefinition("src-attention", ("transformers", "natural-language"), "Attention Is All You Need", ("Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones", "Aidan N. Gomez", "Lukasz Kaiser", "Illia Polosukhin"), 2017, "paper", "https://arxiv.org/abs/1706.03762", "10.48550/arXiv.1706.03762", "Apresenta o Transformer baseado em mecanismos de atenção, sem recorrência ou convolução no núcleo sequencial.", "É o ponto de partida para analisar self-attention, paralelismo e modelos de linguagem modernos."),
    SourceDefinition("src-resnet", ("convolutional-networks", "computer-vision"), "Deep Residual Learning for Image Recognition", ("Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"), 2015, "paper", "https://arxiv.org/abs/1512.03385", "10.48550/arXiv.1512.03385", "Introduz ligações residuais para facilitar a otimização de redes muito profundas.", "Mostra como alterar o caminho do gradiente muda a treinabilidade de arquiteturas visuais."),
    SourceDefinition("src-vit", ("transformers", "computer-vision"), "An Image is Worth 16x16 Words", ("Alexey Dosovitskiy", "Lucas Beyer", "Alexander Kolesnikov"), 2020, "paper", "https://arxiv.org/abs/2010.11929", "10.48550/arXiv.2010.11929", "Aplica uma arquitetura Transformer a sequências de patches de imagem.", "Liga os princípios de atenção à representação visual e à escala de pré-treino."),
    SourceDefinition("src-react", ("agent-architectures", "autonomous-agents"), "ReAct: Synergizing Reasoning and Acting in Language Models", ("Shunyu Yao", "Jeffrey Zhao", "Dian Yu", "Nan Du", "Izhak Shafran", "Karthik Narasimhan", "Yuan Cao"), 2022, "paper", "https://arxiv.org/abs/2210.03629", "10.48550/arXiv.2210.03629", "Intercala raciocínio textual e ações observáveis para atualizar planos com informação do ambiente.", "Oferece um padrão concreto para agentes com ferramentas e trajetórias auditáveis."),
    SourceDefinition("src-reflexion", ("agent-architectures", "agent-memory"), "Reflexion: Language Agents with Verbal Reinforcement Learning", ("Noah Shinn", "Federico Cassano", "Edward Berman", "Ashwin Gopinath", "Karthik Narasimhan", "Shunyu Yao"), 2023, "paper", "https://arxiv.org/abs/2303.11366", "10.48550/arXiv.2303.11366", "Usa feedback linguístico e memória episódica para melhorar tentativas futuras sem atualizar pesos.", "Ajuda a separar reflexão operacional de treino estatístico e a avaliar memória de agentes."),
    SourceDefinition("src-generative-agents", ("multi-agent", "agent-memory"), "Generative Agents: Interactive Simulacra of Human Behavior", ("Joon Sung Park", "Joseph C. O'Brien", "Carrie J. Cai", "Meredith Ringel Morris", "Percy Liang", "Michael S. Bernstein"), 2023, "paper", "https://arxiv.org/abs/2304.03442", "10.48550/arXiv.2304.03442", "Explora agentes com memória, reflexão e planeamento num ambiente social simulado.", "Permite discutir arquiteturas multiagente, avaliação qualitativa e limites de generalização."),
    SourceDefinition("src-rag", ("natural-language", "agent-memory"), "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", ("Patrick Lewis", "Ethan Perez", "Aleksandra Piktus"), 2020, "paper", "https://arxiv.org/abs/2005.11401", "10.48550/arXiv.2005.11401", "Combina recuperação de documentos com geração condicionada para tarefas intensivas em conhecimento.", "É base para compreender proveniência, índice, recuperação e síntese ancorada."),
    SourceDefinition("src-unet", ("computer-vision", "health-app"), "U-Net: Convolutional Networks for Biomedical Image Segmentation", ("Olaf Ronneberger", "Philipp Fischer", "Thomas Brox"), 2015, "paper", "https://arxiv.org/abs/1505.04597", "10.48550/arXiv.1505.04597", "Arquitetura encoder-decoder com skip connections para segmentação com poucos exemplos anotados.", "Liga desenho de CNNs, localização espacial e aplicação biomédica."),
    SourceDefinition("src-sklearn", ("classical-ml", "data-practice"), "scikit-learn User Guide", ("scikit-learn contributors",), 2026, "documentation", "https://scikit-learn.org/stable/user_guide.html", None, "Documentação oficial de estimadores, pipelines, pré-processamento, seleção e avaliação.", "Aproxima teoria e uso seguro, incluindo leakage, validação e composição de pipelines."),
    SourceDefinition("src-stanford-ai-courses", ("artificial-intelligence", "applications"), "Stanford Artificial Intelligence Courses", ("Stanford AI Lab",), 2026, "course", "https://ai.stanford.edu/stanford-ai-courses/", None, "Índice de cursos autorais que cobre ML, RL, NLP, visão, grafos, robótica e decisão.", "Ajuda a validar a amplitude e pré-requisitos da árvore de aprendizagem."),
    SourceDefinition("src-ai-index", ("responsible-ai", "applications"), "Stanford AI Index Report", ("Stanford Institute for Human-Centered AI",), 2026, "report", "https://hai.stanford.edu/ai-index/2026-ai-index-report", None, "Relatório de tendências técnicas, utilização, segurança, ciência, medicina, educação e governação.", "Dá contexto aplicado e métricas atuais sem substituir fontes técnicas primárias."),
    SourceDefinition("src-python-docs", ("python", "prog-foundations", "oop"), "Python 3 Documentation", ("Python Software Foundation",), 2026, "documentation", "https://docs.python.org/3/", None, "Referência oficial da linguagem Python, biblioteca padrão, tutorial e glossário.", "É a fonte normativa para sintaxe, semântica e comportamento das APIs incluídas."),
    SourceDefinition("src-fluent-python", ("python", "oop", "data-structures"), "Fluent Python, 2nd Edition", ("Luciano Ramalho",), 2022, "book", "https://www.oreilly.com/library/view/fluent-python-2nd/9781492056348/", None, "Explora o modelo de dados e padrões idiomáticos de Python moderno.", "Aprofunda a ligação entre os protocolos da linguagem e código claro e eficaz."),
    SourceDefinition("src-postgresql", ("databases",), "PostgreSQL Documentation", ("PostgreSQL Global Development Group",), 2026, "documentation", "https://www.postgresql.org/docs/current/", None, "Documentação oficial do sistema relacional PostgreSQL e da linguagem SQL suportada.", "Serve de referência operacional para consultas, índices, transações e tipos."),
    SourceDefinition("src-mdn", ("web",), "MDN Web Docs", ("Mozilla contributors",), 2026, "documentation", "https://developer.mozilla.org/", None, "Referência aberta para HTML, CSS, JavaScript e APIs da plataforma Web.", "Liga conceitos da Web a exemplos compatíveis e informação de interoperabilidade."),
    SourceDefinition("src-numpy", ("data-practice", "linear-algebra"), "NumPy Documentation", ("NumPy developers",), 2026, "documentation", "https://numpy.org/doc/stable/", None, "Referência oficial para arrays, broadcasting, álgebra linear e computação vetorizada.", "Permite verificar contratos, formas, tipos e semântica das operações numéricas."),
    SourceDefinition("src-pandas", ("data-practice",), "pandas Documentation", ("pandas development team",), 2026, "documentation", "https://pandas.pydata.org/docs/", None, "Referência oficial para dados tabulares, índices, agregações e séries temporais.", "Apoia pipelines reproduzíveis e a compreensão das transformações de dados."),
    SourceDefinition("src-pytorch-autograd", ("deep-learning", "neural-networks"), "PyTorch Autograd Documentation", ("PyTorch contributors",), 2026, "documentation", "https://pytorch.org/docs/stable/autograd.html", None, "Documentação oficial da diferenciação automática e do grafo computacional do PyTorch.", "Relaciona backpropagation, gradientes acumulados e execução concreta."),
    SourceDefinition("src-django", ("web", "databases", "software-engineering"), "Django 6.0 Documentation", ("Django Software Foundation",), 2026, "documentation", "https://docs.djangoproject.com/en/6.0/contents/", None, "Documentação oficial sobre projetos, modelos, views, templates, testes, segurança, migrações e deployment em Django.", "Orienta um percurso completo sem confundir responsabilidades do framework, da base de dados e do protocolo Web."),
    SourceDefinition("src-fastapi", ("web", "software-engineering"), "FastAPI Tutorial — User Guide", ("FastAPI contributors",), 2026, "documentation", "https://fastapi.tiangolo.com/tutorial/", None, "Tutorial oficial progressivo para APIs tipadas, validação, dependências, segurança, testes e OpenAPI.", "Liga contratos Python e HTTP a uma implementação verificável, deixando tópicos avançados para depois dos fundamentos."),
    SourceDefinition("src-flask", ("web", "software-engineering"), "Flask Documentation", ("Pallets contributors",), 2026, "documentation", "https://flask.palletsprojects.com/en/stable/", None, "Guia oficial do microframework Flask, incluindo routing, contexto, templates, testes, configuração e lifecycle.", "Permite comparar uma arquitetura explícita e incremental com frameworks Python mais integrados."),
    SourceDefinition("src-sqlalchemy", ("databases", "python", "software-engineering"), "SQLAlchemy 2.0 Unified Tutorial", ("SQLAlchemy authors and contributors",), 2026, "documentation", "https://docs.sqlalchemy.org/en/20/tutorial/index.html", None, "Tutorial oficial que apresenta Engine, transações, metadata, SQL Expression Language e ORM como camadas relacionadas.", "Ajuda a manter claras as fronteiras entre SQL, unidades de trabalho, objetos persistentes e ciclo transacional."),
    SourceDefinition("src-pytest", ("python", "software-engineering"), "pytest Documentation — Get Started", ("pytest contributors",), 2026, "documentation", "https://docs.pytest.org/en/latest/getting-started.html", None, "Documentação oficial de descoberta de testes, asserts, exceções, fixtures e relatórios de falha.", "Serve de ponte curta entre um contrato observável e uma suite de regressão reproduzível."),
    SourceDefinition("src-mongodb", ("databases",), "MongoDB Database Manual", ("MongoDB documentation team",), 2026, "documentation", "https://www.mongodb.com/docs/manual/contents/", None, "Manual oficial sobre documentos, CRUD, agregação, índices, transações, modelação, replicação, sharding e segurança.", "Permite estudar NoSQL com modelos de consistência e acesso explícitos, sem o reduzir a ausência de tabelas."),
    SourceDefinition("src-git", ("software-engineering",), "Git Reference", ("Git project contributors",), 2026, "documentation", "https://git-scm.com/docs", None, "Referência oficial dos comandos e fluxos para snapshots, branches, merge, inspeção, colaboração e recuperação.", "Liga organização de projetos a histórico verificável e ajuda a escolher operações reversíveis."),
    SourceDefinition("src-docker", ("systems", "software-engineering"), "Docker — Get Started", ("Docker documentation team",), 2026, "documentation", "https://docs.docker.com/get-started/", None, "Percurso oficial sobre contentores, imagens, registries, Dockerfiles e execução isolada.", "Distingue processo isolado de máquina virtual e relaciona empacotamento com reprodução de ambientes."),
    SourceDefinition("src-python-packaging", ("python", "software-engineering"), "Python Packaging User Guide", ("Python Packaging Authority",), 2026, "documentation", "https://packaging.python.org/en/latest/", None, "Guia oficial para ambientes virtuais, dependências, pyproject.toml, builds, formatos e especificações de distribuição.", "Ajuda a transformar código local num projeto reproduzível sem misturar import packages e distribution packages."),
    SourceDefinition("src-python-asyncio", ("python", "systems", "web"), "asyncio — Asynchronous I/O", ("Python Software Foundation",), 2026, "documentation", "https://docs.python.org/3/library/asyncio.html", None, "Referência oficial para coroutines, tasks, event loops, streams, filas e sincronização assíncrona.", "Enquadra async/await como concorrência cooperativa indicada sobretudo para I/O, não como aceleração automática de CPU."),
)


_LOCAL_TOPIC_AREAS = {
    "python-foundations": "prog-foundations",
    "object-oriented-python": "oop",
    "classic-algorithms": "classic-algorithms",
    "data-structures": "data-structures",
    "databases": "databases",
    "classical-ml": "classical-ml",
    "unsupervised-learning": "classical-ml",
    "deep-learning": "deep-learning",
    "reinforcement-learning": "reinforcement-learning",
    "autonomous-agents": "autonomous-agents",
    "computer-vision": "computer-vision",
    "web": "web",
    "mathematics": "math-data",
    "software-engineering": "software-engineering",
}


def _local_library_sources() -> tuple[SourceDefinition, ...]:
    """Load metadata-only references generated from explicitly approved PDFs."""

    asset = Path(__file__).resolve().parents[1] / "presentation" / "assets" / "local-library-catalog.json"
    try:
        payload = json.loads(asset.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ()
    result = []
    for item in payload.get("sources", ()):  # the asset never contains book body
        locators = item.get("locators") or ()
        if not locators:
            continue
        locator = locators[0]
        area_ids = tuple(dict.fromkeys(
            _LOCAL_TOPIC_AREAS[topic]
            for topic in item.get("topics", ())
            if topic in _LOCAL_TOPIC_AREAS
        )) or ("software-engineering",)
        title = str(item.get("title") or "Referência local")[:500]
        root_key = str(locator["root"])
        relative_path = quote(str(locator["relative_path"]), safe="/")
        page_count = max(0, int(item.get("page_count") or 0))
        overview = (
            f"Referência bibliográfica local catalogada para orientar o estudo de "
            f"{', '.join(area_ids)}. O catálogo regista {page_count} páginas, sem "
            "copiar o texto integral nem enunciados da obra."
        )
        result.append(SourceDefinition(
            id=str(item["id"]), area_ids=area_ids, title=title,
            authors=tuple(str(author)[:160] for author in item.get("authors", ())),
            year=None, source_type="book",
            url=f"aprendix-library://{root_key}/{relative_path}", doi=None,
            overview=overview,
            why=("Serve como referência de renome ou material académico validado pelo "
                 "utilizador; o Aprendix produz explicações e práticas originais."),
            access_note="Abre o PDF local apenas se a biblioteca aprovada continuar disponível.",
            license_note=("A obra permanece no diretório privado do utilizador. O Aprendix "
                          "guarda apenas metadados bibliográficos e um localizador relativo."),
            provenance="user-approved-local-library-metadata-2026-08",
        ))
    return tuple(result)


LOCAL_LIBRARY_SOURCES = _local_library_sources()


_OFFICIAL_STDLIB_MODULES = (
    "abc", "argparse", "array", "ast", "asyncio", "bisect", "calendar",
    "collections", "concurrent.futures", "contextlib", "csv", "dataclasses",
    "datetime", "decimal", "difflib", "email", "enum", "fractions",
    "functools", "hashlib", "heapq", "html", "http", "inspect", "io",
    "itertools", "json", "logging", "math", "operator", "os.path", "pathlib",
    "queue", "random", "re", "secrets", "shlex", "sqlite3", "statistics",
    "string", "subprocess", "tempfile", "textwrap", "threading", "time",
    "timeit", "tokenize", "traceback", "typing", "unittest", "urllib.parse",
    "uuid", "warnings", "weakref",
)


def _official_python_api_sources() -> tuple[SourceDefinition, ...]:
    """Catalogue real public APIs from the installed Python documentation set.

    Each record points to an official PSF documentation anchor. Import failures
    are tolerated for reduced mobile runtimes; no network request occurs here.
    """

    area_overrides = {
        "ast": ("python", "classic-algorithms"),
        "asyncio": ("python", "systems"),
        "concurrent.futures": ("python", "systems"),
        "threading": ("python", "systems"),
        "subprocess": ("python", "systems"),
        "sqlite3": ("python", "databases"),
        "math": ("python", "math-data"),
        "statistics": ("python", "probability"),
        "decimal": ("python", "math-data"),
        "fractions": ("python", "math-data"),
        "unittest": ("python", "software-engineering"),
        "logging": ("python", "software-engineering"),
        "traceback": ("python", "software-engineering"),
    }
    records: list[SourceDefinition] = []
    for module_name in _OFFICIAL_STDLIB_MODULES:
        try:
            module = importlib.import_module(module_name)
        except (ImportError, OSError, RuntimeError):
            continue
        for name, value in inspect.getmembers(module):
            if name.startswith("_"):
                continue
            owner = getattr(value, "__module__", "") or ""
            is_public_api = (
                inspect.isfunction(value) or inspect.isclass(value) or inspect.isbuiltin(value)
            )
            if not is_public_api or not (
                owner == module_name or owner.startswith(module_name + ".")
            ):
                continue
            identity = re.sub(r"[^a-z0-9]+", "-", f"{module_name}-{name}".casefold()).strip("-")
            qualified = f"{module_name}.{name}"
            kind = "classe" if inspect.isclass(value) else "função"
            records.append(SourceDefinition(
                id=f"src-pydoc-{identity}"[:160],
                area_ids=area_overrides.get(module_name, ("python",)),
                title=f"{qualified} — Python 3 Documentation",
                authors=("Python Software Foundation",),
                year=2026,
                source_type="documentation",
                url=(
                    f"https://docs.python.org/3/library/{module_name}.html"
                    f"#{qualified}"
                ),
                doi=None,
                overview=(
                    f"Entrada oficial da biblioteca padrão para a {kind} pública "
                    f"{qualified}; define o contrato e o comportamento suportado."
                ),
                why=(
                    "Permite confirmar assinatura, semântica e limitações numa fonte "
                    "normativa, sem depender de exemplos não verificados."
                ),
                access_note="Consultar a documentação oficial da versão Python 3 instalada.",
                license_note="Metadados e ligação para documentação oficial da Python Software Foundation.",
                provenance="python-public-api-official-docs-2026-08",
            ))
    unique = {item.id: item for item in records}
    return tuple(unique[key] for key in sorted(unique))


OFFICIAL_PYTHON_API_SOURCES = _official_python_api_sources()
SOURCES: tuple[SourceDefinition, ...] = (
    *PRIMARY_SOURCES,
    *LOCAL_LIBRARY_SOURCES,
    *OFFICIAL_PYTHON_API_SOURCES,
)


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()


def classify_areas(text: str, *, limit: int = 5) -> tuple[tuple[str, float, str], ...]:
    """Return deterministic, explainable leaf-area assignments."""

    normalized = fold(text)
    scores: list[tuple[float, str, str]] = []
    for area in AREAS:
        if not area.keywords:
            continue
        matched = tuple(keyword for keyword in area.keywords if fold(keyword) in normalized)
        if matched:
            score = min(1.0, 0.52 + 0.12 * len(matched))
            scores.append((score, area.id, ", ".join(matched[:4])))
    scores.sort(key=lambda item: (-item[0], item[1]))
    if not scores:
        scores.append((0.35, "prog-foundations", "fallback pedagógico"))
    return tuple((area_id, score, reason) for score, area_id, reason in scores[:limit])


class PedagogicalReadingAssistant:
    """Bounded extractive summarizer with rigorous concept and math scaffolding."""

    VERSION = "pedagogical-extractive-v1"
    _word = re.compile(r"[A-Za-zÀ-ÿ0-9_+-]{3,}")
    _sentence = re.compile(r"(?<=[.!?])\s+|\n{2,}")
    _math = re.compile(r"(?:[$][^$]{2,}[$])|(?:\b[A-Za-z]\s*=\s*[^\n,.]{2,})")
    _stop = frozenset({"para", "como", "uma", "com", "dos", "das", "the", "and", "that", "from", "this", "with", "por", "que", "não", "nos", "their", "into"})

    @classmethod
    def build(cls, text: str, query: str = "") -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
        clean = re.sub(r"[ \t]+", " ", text).strip()
        sentences = [item.strip() for item in cls._sentence.split(clean) if 35 <= len(item.strip()) <= 1_800]
        if not sentences:
            sentences = [clean[:4_000] or "Conteúdo sem texto extraível."]
        words = [fold(item) for item in cls._word.findall(clean)]
        frequencies = Counter(word for word in words if word not in cls._stop)
        query_terms = {fold(item) for item in cls._word.findall(query)}

        ranked: list[tuple[float, int, str]] = []
        for index, sentence in enumerate(sentences):
            terms = [fold(item) for item in cls._word.findall(sentence)]
            density = sum(frequencies[term] for term in set(terms)) / max(1, len(terms))
            relevance = 2.5 * len(query_terms & set(terms))
            opening = 0.8 if index == 0 else 0.0
            ranked.append((density + relevance + opening, index, sentence))
        chosen = sorted(sorted(ranked, reverse=True)[: min(6, len(ranked))], key=lambda item: item[1])
        key_points = tuple(sentence[:1_200] for _score, _index, sentence in chosen)
        summary = "\n\n".join(key_points)[:12_000]

        formulas = tuple(dict.fromkeys(match.group(0).strip() for match in cls._math.finditer(clean)))[:8]
        math_notes = tuple(
            f"Expressão preservada: {formula}. Identifica entradas, operação e unidade; verifica depois um caso simples e um caso-limite."
            for formula in formulas
        )
        simplified_lines = [
            "IDEIA CENTRAL",
            key_points[0] if key_points else summary,
            "",
            "PASSO A PASSO",
        ]
        simplified_lines.extend(
            f"{index}. {point}" for index, point in enumerate(key_points[1:] or key_points, start=1)
        )
        if math_notes:
            simplified_lines.extend(("", "MATEMÁTICA GUIADA", *math_notes))
        simplified_lines.extend((
            "",
            "COMO VALIDAR A COMPREENSÃO",
            "Explica o mecanismo por palavras tuas, identifica os pressupostos e testa um exemplo pequeno antes de generalizar.",
        ))
        return summary, "\n".join(simplified_lines)[:20_000], key_points, math_notes


def area_depths() -> dict[str, int]:
    parents = {area.id: area.parent_id for area in AREAS}
    result: dict[str, int] = {}
    for area_id in parents:
        depth, cursor, seen = 0, parents[area_id], {area_id}
        while cursor is not None and cursor not in seen:
            seen.add(cursor); depth += 1; cursor = parents.get(cursor)
        result[area_id] = depth
    return result


def ancestors(area_id: str) -> tuple[str, ...]:
    parents = {area.id: area.parent_id for area in AREAS}
    values: list[str] = []
    cursor = parents.get(area_id)
    while cursor:
        values.append(cursor); cursor = parents.get(cursor)
    return tuple(values)


def descendants(area_id: str, areas: Iterable[AreaDefinition] = AREAS) -> tuple[str, ...]:
    children: dict[str | None, list[str]] = {}
    for area in areas:
        children.setdefault(area.parent_id, []).append(area.id)
    result: list[str] = []
    stack = list(reversed(children.get(area_id, [])))
    while stack:
        current = stack.pop(); result.append(current)
        stack.extend(reversed(children.get(current, [])))
    return tuple(result)
