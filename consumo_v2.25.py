import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import json
import calendar
import re

# Função para formatar CNPJ
def format_cnpj(cnpj):
    cnpj = re.sub(r'\D', '', str(cnpj))
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

# Função para carregar dados do JSON
@st.cache_data
def carregar_dados():
    with open("dados_ccee.json", "r") as f:
        dados = json.load(f)
    return dados

# Função para criar DataFrame a partir dos dados
@st.cache_data
def criar_dataframe(dados):
    registros = []
    for item in dados:
        cnpj = item["cnpjRaiz"]
        nome_empresa = item["razaoSocial"]
        submercado = item["submercado"]
        unidade_consumidora = item["unidadeConsumidora"]
        historico = item["historico"]

        for entrada in historico:
            data = datetime.strptime(entrada["data"], "%Y-%m-%dT%H:%M:%S")
            mes_ano = f"{calendar.month_abbr[data.month]}/{data.year}"
            consumo = entrada["consumo"]
            registros.append({
                "CNPJ": cnpj,
                "Empresa": nome_empresa,
                "Submercado": submercado,
                "Unidade Consumidora": unidade_consumidora,
                "Data": data,
                "Mês/Ano": mes_ano,
                "Consumo (kWh)": consumo
            })

    df = pd.DataFrame(registros)
    df["CNPJ"] = df["CNPJ"].apply(format_cnpj)
    return df

# Função para aplicar filtros
def aplicar_filtros(df, empresa_selecionada, data_inicio, data_fim):
    if empresa_selecionada:
        df = df[df["Empresa"] == empresa_selecionada]
    if data_inicio:
        df = df[df["Data"] >= pd.to_datetime(data_inicio)]
    if data_fim:
        df = df[df["Data"] <= pd.to_datetime(data_fim)]
    return df

# Função para calcular a média mensal e alertar sobre desvios
def verificar_flexibilidade(df, flexibilidade_percentual):
    media_mensal = df.groupby("Mês/Ano")["Consumo (kWh)"].mean().reset_index()
    media_total = df["Consumo (kWh)"].mean()
    limite_inferior = media_total * (1 - flexibilidade_percentual / 100)
    limite_superior = media_total * (1 + flexibilidade_percentual / 100)

    media_mensal["Alerta"] = media_mensal["Consumo (kWh)"].apply(
        lambda x: "Abaixo do limite" if x < limite_inferior else ("Acima do limite" if x > limite_superior else "Dentro do limite")
    )

    return media_mensal, limite_inferior, limite_superior

# Função principal
def main():
    st.title("📊 Análise de Consumo de Energia")
    
    dados = carregar_dados()
    df = criar_dataframe(dados)

    st.sidebar.header("Filtros")

    empresas = sorted(df["Empresa"].unique())
    empresa_selecionada = st.sidebar.selectbox("Selecione a empresa", [""] + empresas)
    
    data_min = df["Data"].min().date()
    data_max = df["Data"].max().date()

    data_inicio = st.sidebar.date_input("Data inicial", value=data_min, min_value=data_min, max_value=data_max)
    data_fim = st.sidebar.date_input("Data final", value=data_max, min_value=data_min, max_value=data_max)

    df_filtrado = aplicar_filtros(df, empresa_selecionada, data_inicio, data_fim)

    flexibilidade = st.sidebar.slider("Flexibilidade (%)", min_value=0, max_value=100, value=10)

    st.subheader("📈 Consumo Filtrado")
    st.dataframe(df_filtrado)

    if not df_filtrado.empty:
        st.subheader("📊 Média de Consumo Mensal e Alerta de Flexibilidade")

        media_mensal, limite_inf, limite_sup = verificar_flexibilidade(df_filtrado, flexibilidade)

        st.write(f"**Limite Inferior:** {limite_inf:.2f} kWh")
        st.write(f"**Limite Superior:** {limite_sup:.2f} kWh")

        st.dataframe(media_mensal)

        # Gráfico de barras
        st.bar_chart(data=media_mensal.set_index("Mês/Ano")["Consumo (kWh)"])

        # Exibição da tabela dos últimos 12 meses
        st.subheader("📆 Últimos 12 meses de consumo")
        ultimos_12 = df_filtrado.sort_values(by="Data", ascending=False).head(12)
        st.dataframe(ultimos_12[["Empresa", "Submercado", "Unidade Consumidora", "CNPJ", "Mês/Ano", "Consumo (kWh)"]])
    else:
        st.warning("Nenhum dado disponível para os filtros selecionados.")

if __name__ == "__main__":
    main()
