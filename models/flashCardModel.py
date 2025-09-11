from agno.agent import Agent
from agno.models.groq import Groq
from fastapi import Depends, HTTPException
from controllers.auth import getCurrentUser
from connection import prismaConnection
import json
import tiktoken
from dotenv import load_dotenv
load_dotenv()

# Definição do modelo
model = Groq(id="openai/gpt-oss-120b")

# Criação do agente
flashcard_agent = Agent(
    name="flashcard_agent",
    model=model,
    instructions="""
### CONTEXTO E OBJETIVO ###
Você é um designer instrucional especialista em criar materiais de aprendizagem eficazes. Sua tarefa é analisar o texto fornecido e criar um conjunto de flashcards de alta qualidade para ajudar um estudante a memorizar os conceitos mais importantes.

### FORMATO DE SAÍDA OBRIGATÓRIO ###
A sua resposta DEVE ser exclusivamente um array JSON válido. Não inclua explicações, comentários, ou qualquer texto antes do `[` de abertura ou depois do `]` de fechamento.

A estrutura de cada objeto flashcard no array deve ser:
{
  "front": "string",
  "back": "string"
}

### REGRAS PARA O CONTEÚDO DOS FLASHCARDS ###
1.  **Quantidade**: Gere exatamente [20] flashcards.
2.  **Relevância**: Foque APENAS na informação mais crítica e fundamental do texto. Ignore detalhes triviais, exemplos secundários ou informações de preenchimento. Priorize:
    - Definições de termos-chave.
    - Conceitos fundamentais e suas explicações.
    - Datas, nomes ou dados importantes.
    - Relações de causa e efeito.
    - Etapas de um processo ou sistema.
3.  **Qualidade do "Front"**: O campo "front" deve ser uma pergunta clara e concisa ou um termo-chave. Prefira frases nominais a perguntas completas (Ex: "Principal causa da Revolução Industrial" em vez de "Qual foi a principal causa da Revolução Industrial?").
4.  **Qualidade do "Back"**: O campo "back" deve conter a resposta completa, precisa e direta, mas sem ser excessivamente longo.
5.  **Idioma**: O idioma dos flashcards deve ser o mesmo do texto de origem.
"""
)


# Exibindo resultado


async def processFlashcards(text: str, current_user: dict = Depends(getCurrentUser)):
    # Verificar se o usuário está autenticado
    if current_user is None:
        raise HTTPException(status_code=401, detail="Usuário não autenticado")
    
    # Verificar se o usuário tem tokens suficientes
    user_id = current_user['id']
    user = await prismaConnection.prisma.user.find_unique(where={'id': user_id})
    
    if not user or user.tokens <= 0:
        raise HTTPException(status_code=400, detail="Tokens insuficientes")
    
    # Executando o agente e salvando resposta
    num_tokens = contar_tokens(text)
    # if num_tokens > 50:
    #     raise HTTPException(status_code=400, detail="Tokens acima de 50")
    response = flashcard_agent.run(text)
    raw_content = response.content
    flashcards = json.loads(raw_content)
    
    # Remover 1 token do usuário
    await prismaConnection.prisma.user.update(
        where={'id': user_id},
        data={'tokens': user.tokens - 1},
    )
    
    return flashcards





def contar_tokens(texto, modelo="gpt-3.5-turbo"):
    """Conta o número de tokens em um texto para um modelo específico."""
    try:
        encoding = tiktoken.encoding_for_model(modelo)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    num_tokens = len(encoding.encode(texto))
    return num_tokens
