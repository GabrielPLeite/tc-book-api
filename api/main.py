# api/main.py
from fastapi import FastAPI, Query, HTTPException
from typing import Optional, List
import pandas as pd
import os
import uvicorn

# 1. Configuração e Carregamento de Dados
app = FastAPI(
    title="Book Recommendation API (v1)",
    description="API pública para consulta de livros, fonte de dados para modelos de ML.",
    version="1.0.0"
)

# Caminho absoluto para o arquivo CSV a partir do diretório raiz do projeto
# O os.path.join() garante que o caminho funcione no Windows, Linux e Mac.
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'books.csv')
BOOKS_DATA = None

def load_data():
    """Carrega os dados do CSV uma vez na inicialização."""
    global BOOKS_DATA
    try:
        # Carrega o CSV e garante que a coluna 'id' seja um número inteiro
        BOOKS_DATA = pd.read_csv(DATA_PATH).astype({'id': int})
        print(f"Dados carregados: {len(BOOKS_DATA)} livros.")
    except FileNotFoundError:
        # Levanta um erro que será capturado pelo Uvicorn se o arquivo não existir
        raise RuntimeError(f"Arquivo de dados não encontrado em: {DATA_PATH}. Execute o scraping (scripts/scraping.py) primeiro.")
    except Exception as e:
        raise RuntimeError(f"Erro ao carregar dados: {e}")

# Executa o carregamento de dados
try:
    load_data()
except RuntimeError as e:
    print(f"ALERTA: Falha no carregamento inicial dos dados. API operacional, mas endpoints de dados falharão. Erro: {e}")
    # Se falhar, o BOOKS_DATA permanece None, mas a API pode iniciar para o /health.


# 2. Endpoints Core Obrigatórios
# GET /api/v1/health
@app.get("/api/v1/health", tags=["Core"])
def health_check():
    """Verifica o status da API e conectividade com os dados."""
    data_status = "ok" if BOOKS_DATA is not None and not BOOKS_DATA.empty else "data_error"
    
    if data_status == "ok":
        return {"status": "ok", "message": "API is operational and data is loaded."}
    else:
        # Retorna status 200, mas com alerta sobre os dados (boas práticas de health check)
        return {"status": "warning", "message": "API is operational, but data could not be loaded. Run scraper.", "data_status": data_status}


# GET /api/v1/books
@app.get("/api/v1/books", tags=["Core"])
def list_books():
    """Lista todos os livros disponíveis na base de dados."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    return BOOKS_DATA.to_dict(orient="records")


# GET /api/v1/books/{id}
@app.get("/api/v1/books/{id}", tags=["Core"])
def get_book_details(id: int):
    """Retorna detalhes completos de um livro específico pelo ID."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    book = BOOKS_DATA[BOOKS_DATA['id'] == id]
    
    if book.empty:
        raise HTTPException(status_code=404, detail=f"Book with ID {id} not found.")
        
    return book.iloc[0].to_dict()


# GET /api/v1/categories
@app.get("/api/v1/categories", tags=["Core"])
def list_categories():
    """Lista todas as categorias de livros disponíveis."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    categories = BOOKS_DATA['category'].unique().tolist()
    return {"categories": categories, "count": len(categories)}


# GET /api/v1/books/search?title={title}&category={category}
@app.get("/api/v1/books/search", tags=["Core"])
def search_books(
    title: Optional[str] = Query(None, description="Busca parcial por título"),
    category: Optional[str] = Query(None, description="Busca exata por categoria")
):
    """Busca livros por título e/ou categoria."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    results = BOOKS_DATA.copy()
    
    # Filtro por Título (case-insensitive, busca parcial)
    if title:
        title = title.lower()
        results = results[results['title'].str.lower().str.contains(title, na=False)]
        
    # Filtro por Categoria (case-insensitive, busca exata)
    if category:
        category = category.lower()
        results = results[results['category'].str.lower() == category]
        
    if results.empty:
        return {"message": "No books found matching the criteria.", "results": []}

    return results.to_dict(orient="records")


# 3. Endpoints Opcionais (Insights)

# GET /api/v1/stats/overview
@app.get("/api/v1/stats/overview", tags=["Insights"])
def get_stats_overview():
    """Estatísticas gerais da coleção (total de livros, preço médio, distribuição de ratings)."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    total_books = len(BOOKS_DATA)
    # Preço médio
    avg_price = BOOKS_DATA['price'].mean()
    # Distribuição de ratings (contagem de cada estrela)
    rating_distribution = BOOKS_DATA['rating'].value_counts().sort_index().to_dict()

    return {
        "total_books": total_books,
        "average_price": round(avg_price, 2),
        "rating_distribution": rating_distribution
    }


# GET /api/v1/stats/categories
@app.get("/api/v1/stats/categories", tags=["Insights"])
def get_stats_categories():
    """Estatísticas detalhadas por categoria (quantidade de livros, preço médio por categoria)."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    # Agrupa por categoria para contar o total e calcular a média de preço
    category_stats = BOOKS_DATA.groupby('category').agg(
        count=('category', 'size'),
        average_price=('price', 'mean')
    ).reset_index()

    # Formata o resultado para JSON
    stats_dict = category_stats.to_dict(orient='records')

    # Arredonda o preço médio
    for item in stats_dict:
        item['average_price'] = round(item['average_price'], 2)
        
    return {"category_stats": stats_dict}


# GET /api/v1/books/top-rated
@app.get("/api/v1/books/top-rated", tags=["Insights"])
def get_top_rated(limit: int = Query(10, description="Número máximo de livros a retornar.")):
    """Lista os livros com melhor avaliação (rating mais alto)."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    # Filtra por rating máximo (5 estrelas) e depois pega o topo pela disponibilidade
    top_rated = BOOKS_DATA[BOOKS_DATA['rating'] == 5]
    
    # Se houver muitos livros com rating 5, podemos ordenar por preço ou ID, mas a prioridade é a avaliação.
    # Apenas limitamos o número de resultados.
    
    return top_rated.head(limit).to_dict(orient="records")


# GET /api/v1/books/price-range?min={min}&max={max}
@app.get("/api/v1/books/price-range", tags=["Insights"])
def filter_by_price_range(
    min_price: float = Query(0.0, description="Preço mínimo para filtrar"),
    max_price: float = Query(float('inf'), description="Preço máximo para filtrar")
):
    """Filtra livros dentro de uma faixa de preço específica."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    # Filtra o DataFrame
    filtered_books = BOOKS_DATA[
        (BOOKS_DATA['price'] >= min_price) & 
        (BOOKS_DATA['price'] <= max_price)
    ]
    
    if filtered_books.empty:
        return {"message": f"No books found in the price range £{min_price} to £{max_price}.", "results": []}

    return filtered_books.to_dict(orient="records")


# Código para rodar diretamente (bom para debug, mas o uvicorn é melhor)
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)