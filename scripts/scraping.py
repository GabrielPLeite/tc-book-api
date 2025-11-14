# scripts/scraping.py
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import os

# --- Configuração ---
BASE_URL = 'https://books.toscrape.com/'
DATA_FILE = 'data/books.csv'
RATING_MAP = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5}

def clean_price(price_str):
    """Limpa a string de preço, removendo caracteres indesejados (como símbolos de moeda ou codificação errada) e a converte para float."""
    
    cleaned_str = re.sub(r'[^\d.]', '', price_str)
    
    try:
        return float(cleaned_str)
    except ValueError:
        print(f"Aviso: Não foi possível converter o preço original '{price_str}' após limpeza para '{cleaned_str}'. Usando 0.0.")
        return 0.0

def get_product_details(soup):
    """Extrai detalhes do livro de uma página de produto."""
    product_table = soup.find('table', class_='table table-striped').find_all('td')
    
    # Preço: Índice 3 (Price (incl. tax))
    price = clean_price(product_table[3].text)
    
    # Disponibilidade: Índice 5
    availability_str = product_table[5].text
    match = re.search(r'\d+', availability_str)
    availability = int(match.group(0)) if match else 0
    
    # Categoria: Breadcrumb (Índice 3)
    breadcrumb = soup.find('ul', class_='breadcrumb').find_all('li')
    category = breadcrumb[3].text.strip() 

    return price, availability, category

def scrape_page(url, books_data):
    """Scrapeia todos os livros de uma página e navega para a próxima."""
    
    print(f"Scraping página: {url}")
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Erro ao acessar {url}")
        return None
        
    list_soup = BeautifulSoup(response.text, 'html.parser')
    articles = list_soup.find_all('article', class_='product_pod')
    
    for article in articles:
        # Título e URL
        title_tag = article.h3.a
        title = title_tag['title']
        book_relative_url = title_tag['href']
        
        # Link da Imagem
        image_relative_url = article.find('img')['src']
        image_url = BASE_URL + image_relative_url.replace('../..', '')
        
        # Rating (Estrelas)
        star_rating = article.p['class'][1]
        rating = RATING_MAP.get(star_rating, 0)
        
        # Corrigir o path do livro e extrair detalhes na página individual
        book_url_path = 'catalogue/' + book_relative_url.replace('../', '') if 'catalogue' not in book_relative_url else book_relative_url
        detail_response = requests.get(BASE_URL + book_url_path)
        detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
        
        price, availability, category = get_product_details(detail_soup)

        books_data.append({
            'title': title,
            'price': price,
            'rating': rating,
            'availability': availability,
            'category': category,
            'image_url': image_url,
        })
        
    # Encontrar link para a próxima página
    next_page_tag = list_soup.find('li', class_='next')
    if next_page_tag:
        # Retorna o URL relativo da próxima página
        return 'catalogue/' + next_page_tag.a['href']
    else:
        return None

def run_scraper():
    """Função principal para coordenar o scraping de todas as páginas."""
    books_list = []
    # Inicia na página 1
    current_page_url = BASE_URL + 'catalogue/page-1.html'
    
    while current_page_url:
        next_page_path = scrape_page(current_page_url, books_list)
        
        if next_page_path:
            current_page_url = BASE_URL + next_page_path
        else:
            current_page_url = None
            
    # 2. Salvar os Dados (Entregável)
    if not os.path.exists('data'):
        os.makedirs('data')
        
    df = pd.DataFrame(books_list)
    # Adicionar ID Sequencial (Necessário para o endpoint /books/{id})
    df.index.name = 'id'
    df = df.reset_index()
    df['id'] = df['id'] + 1 
    
    df.to_csv(DATA_FILE, index=False) # Dados armazenados localmente em um arquivo CSV [cite: 25]
    print(f"\n✅ Scraping concluído. {len(df)} livros salvos em {DATA_FILE}")

if __name__ == '__main__':
    run_scraper()