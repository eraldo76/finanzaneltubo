from settings import OPENAI_API_KEY, OPENAI_MODEL
import openai
import json

# Imposta la chiave API
openai.api_key = OPENAI_API_KEY

# Funzione per chiamare OpenAI


def openai_call(prompt):
    response = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "Sei un copywriter ed esperto in SEO e devi creare un articolo da un testo e da una parola chiave suggerita"},
            {"role": "user", "content": prompt}
        ]
    )
    print(response)  # Stampa la risposta completa
    return response.choices[0].message['content'].strip()


def summarize_transcription(transcription, keyword):
    prompt = f"Riassumi la seguente trascrizione: '{transcription}'. Considera la parola chiave: '{keyword}'."
    summary = openai_call(prompt)
    return summary


def step2(summary, keyword):
    # Crea un prompt per OpenAI utilizzando il riassunto e la keyword forniti
    prompt = f"""Sei un copywriter e seo expert e da questo testo: '{summary}' e da questa parola chiave : '{keyword}', devi generare il 'title', la 'meta_description', l'h1, e l'article_intro'. La risposta deve essere un json in cui è presente il contenuto richiesto."""

    print("Prompt creato:", prompt)  # Stampa il prompt creato

    # Chiama la funzione `openai_call` per ottenere una risposta da OpenAI
    response_text = openai_call(prompt)

    # Stampa il tipo della risposta ricevuta da OpenAI per verificare il suo formato
    print("Tipo della Risposta OpenAI:", type(response_text))
    print("Risposta OpenAI:", response_text)  # Stampa la risposta di OpenAI

    # Controlla se la risposta è una stringa e, in tal caso, carica come JSON. Altrimenti, considera già come dizionario.
    if isinstance(response_text, str):
        response_data = json.loads(response_text)
    else:
        response_data = response_text

    # Estrae i dati richiesti dal dizionario
    title = response_data.get("title", "")
    meta_description = response_data.get("meta_description", "")
    h1 = response_data.get("h1", "")
    article_intro = response_data.get("article_intro", "")

    print("Title:", title)  # Stampa il title estratto
    # Stampa la meta description estratta
    print("Meta Description:", meta_description)
    print("H1:", h1)  # Stampa l'H1 estratto
    print("Article Intro:", article_intro)  # Stampa l'article intro estratto

    # Restituisce i dati sotto forma di un dizionario
    return {
        'title': title,
        'meta_description': meta_description,
        'h1': h1,
        'article_intro': article_intro
    }

# Ora, puoi eseguire la funzione step2 e verificare i risultati.
# Assicurati di avere la funzione `openai_call` correttamente implementata nel tuo script.


def step3(summary, keyword):
    prompt = f"""
Sei un copywriter e seo expert. Basandoti su questo testo: '{summary}' e su questa parola chiave: '{keyword}', crea una lista di AL MASSIMO 5 argomenti o punti salienti su cui sviluppare ulteriormente. La risposta deve essere strutturata come un array JSON, dove ogni elemento dell'array è un oggetto con un campo "title" e un campo "description". Ecco un esempio di formato che desidero: 
[{{"title": "Titolo Esempio 1", "description": "Descrizione Esempio 1"}},
 {{"title": "Titolo Esempio 2", "description": "Descrizione Esempio 2"}}]
"""

    response_text = openai_call(prompt)
    print("OpenAI Response:", response_text)

    # Se `openai_call` restituisce una stringa, tentiamo di convertirla in un dizionario.
    if isinstance(response_text, str):
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            print("Invalid JSON received:", response_text)
            return []
    else:
        response_data = response_text

    # Poiché ci aspettiamo una lista come risposta, possiamo semplicemente restituirla.
    return response_data


# Generare contenuto per ogni OUTLINE

def step4(transcription, keyword, outlines):
    titles = [outline['title'] for outline in outlines]
    all_titles = ', '.join(titles[:-1]) + ' e ' + \
        titles[-1] if len(titles) > 1 else titles[0]
    description = ", ".join([outline['description'] for outline in outlines])

    prompt = f"""Sei un copywriter e seo expert. Basandoti su questo testo: '{transcription}' e su questa parola chiave: '{keyword}', prendendo in considerazione questi titoli: '{all_titles}' e queste descrizioni: '{description}', crea un contenuto non inferiore a 1500 parole in cui i titoli sono racchiusi dal tag <h2> ."""

    content = openai_call(prompt)
    return content
