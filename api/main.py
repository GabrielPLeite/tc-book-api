from fastapi import FastAPI, Query, HTTPException
from typing import Optional, Dict, Any, List
import pandas as pd
import os

# --- 1. Constantes e Configurações ---
API_VERSION = "v1"
API_TITLE = "Book Recommendation API"
API_DESCRIPTION = "API pública para consulta de livros, fonte de dados para modelos de ML."
API_PREFIX = f"/api/{API_VERSION}"

# Define o caminho absoluto para o arquivo CSV, subindo um nível (..) do diretório 'api'
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'books.csv')
BOOKS_DATA: Optional[pd.DataFrame] = None

# --- 2. Carregamento de Dados ---

def load_data() -> pd.DataFrame:
    """
    Carrega o arquivo CSV na memória e realiza pré-processamento inicial.
    Levanta um erro se o arquivo não for encontrado, impedindo a inicialização da API.
    """
    try:
        # Tenta ler o arquivo de dados
        df = pd.read_csv(DATA_PATH)
        # Garante que a coluna 'id' seja tratada como inteiro
        df['id'] = df.index + 1
        print(f"Dados carregados: {len(df)} livros.")
        return df
    except FileNotFoundError:
        # Erro fatal: a API não pode funcionar sem a fonte de dados.
        raise RuntimeError(
            f"Arquivo de dados não encontrado em: {DATA_PATH}. Execute o scraping (scripts/scraping.py) primeiro."
        )
    except Exception as e:
        raise RuntimeError(f"Erro inesperado ao carregar dados: {e}")

# Tenta carregar os dados na inicialização do servidor
try:
    BOOKS_DATA = load_data()
except RuntimeError as e:
    # Em produção, o Uvicorn irá capturar este erro e não iniciará a aplicação.
    # Aqui, apenas imprimimos o alerta no log.
    print(f"ALERTA CRÍTICO: Falha no carregamento inicial dos dados. Erro: {e}")

# --- 3. Inicialização do FastAPI ---

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
)

# --- 4. Endpoints Core Obrigatórios ---

@app.get(f"{API_PREFIX}/health", tags=["Core"])
def health_check() -> Dict[str, Any]:
    """Verifica o status da API e conectividade com os dados."""
    data_loaded = BOOKS_DATA is not None and not BOOKS_DATA.empty
    
    if data_loaded:
        return {"status": "ok", "message": "API operacional e dados carregados com sucesso."}
    else:
        # Em um cenário de deploy, se o data_loaded for False, algo falhou no build/startup
        raise HTTPException(status_code=503, detail="Service Unavailable: Falha no carregamento dos dados.")


@app.get(f"{API_PREFIX}/books", tags=["Core"])
def list_books() -> List[Dict[str, Any]]:
    """Lista todos os livros disponíveis na base de dados."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    # Retorna a lista de registros como JSON
    return BOOKS_DATA.to_dict(orient="records")


@app.get(f"{API_PREFIX}/books/{{id}}", tags=["Core"])
def get_book_details(id: int) -> Dict[str, Any]:
    """Retorna detalhes completos de um livro específico pelo ID."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    # Busca o livro pelo ID
    book = BOOKS_DATA[BOOKS_DATA['id'] == id]
    
    if book.empty:
        raise HTTPException(status_code=404, detail=f"Livro com ID {id} não encontrado.")
        
    # Retorna o primeiro (e único) resultado
    return book.iloc[0].to_dict()


@app.get(f"{API_PREFIX}/categories", tags=["Core"])
def list_categories() -> Dict[str, Any]:
    """Lista todas as categorias de livros disponíveis."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    categories = BOOKS_DATA['category'].unique().tolist()
    return {"categories": categories, "count": len(categories)}


@app.get(f"{API_PREFIX}/books/search", tags=["Core"])
def search_books(
    title: Optional[str] = Query(None, description="Busca parcial e case-insensitive por título"),
    category: Optional[str] = Query(None, description="Busca exata e case-insensitive por categoria")
) -> List[Dict[str, Any]]:
    """Busca livros por título e/ou categoria."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    results = BOOKS_DATA.copy()
    
    # Filtro por Título
    if title:
        title_lower = title.lower()
        results = results[results['title'].str.lower().str.contains(title_lower, na=False)]
        
    # Filtro por Categoria
    if category:
        category_lower = category.lower()
        results = results[results['category'].str.lower() == category_lower]
        
    if results.empty:
        return {"message": "Nenhum livro encontrado correspondendo aos critérios.", "results": []}

    return results.to_dict(orient="records")

# --- 5. Endpoints Opcionais (Insights para ML/Análise) ---

@app.get(f"{API_PREFIX}/stats/overview", tags=["Insights"])
def get_stats_overview() -> Dict[str, Any]:
    """Estatísticas gerais da coleção (total de livros, preço médio, distribuição de ratings)."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    avg_price = BOOKS_DATA['price'].mean()
    rating_distribution = BOOKS_DATA['rating'].value_counts().sort_index().to_dict()

    return {
        "total_books": len(BOOKS_DATA),
        "average_price": round(avg_price, 2),
        "rating_distribution": rating_distribution
    }


@app.get(f"{API_PREFIX}/stats/categories", tags=["Insights"])
def get_stats_categories() -> Dict[str, Any]:
    """Estatísticas detalhadas por categoria (quantidade de livros, preço médio por categoria)."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")
        
    category_stats = BOOKS_DATA.groupby('category').agg(
        count=('category', 'size'),
        average_price=('price', 'mean')
    ).reset_index()

    # Formatação e arredondamento para JSON
    stats_dict = category_stats.to_dict(orient='records')
    for item in stats_dict:
        item['average_price'] = round(item['average_price'], 2)
        
    return {"category_stats": stats_dict}


@app.get(f"{API_PREFIX}/books/top-rated", tags=["Insights"])
def get_top_rated(limit: int = Query(10, description="Número máximo de livros a retornar.")) -> List[Dict[str, Any]]:
    """Lista os livros com melhor avaliação (rating mais alto, 5 estrelas)."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    # Filtra apenas livros com 5 estrelas
    top_rated = BOOKS_DATA[BOOKS_DATA['rating'] == 5]
    
    # Retorna o topo limitado pelo parâmetro 'limit'
    return top_rated.head(limit).to_dict(orient="records")


@app.get(f"{API_PREFIX}/books/price-range", tags=["Insights"])
def filter_by_price_range(
    min_price: float = Query(0.0, description="Preço mínimo para filtrar"),
    max_price: float = Query(float('inf'), description="Preço máximo para filtrar")
) -> List[Dict[str, Any]]:
    """Filtra livros dentro de uma faixa de preço específica."""
    if BOOKS_DATA is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: Data not loaded.")

    # Filtra o DataFrame
    filtered_books = BOOKS_DATA[
        (BOOKS_DATA['price'] >= min_price) & 
        (BOOKS_DATA['price'] <= max_price)
    ]
    
    if filtered_books.empty:
        return {"message": f"Nenhum livro encontrado na faixa de preço £{min_price} a £{max_price}.", "results": []}

    return filtered_books.to_dict(orient="records")