import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import requests
import time
from calendar import monthrange
import re

st.set_page_config(layout="wide")
st.title("📊 Análise de Consumo de Energia")

# URLs das APIs
#resource_id_2024 = "b854f7bc-94a3-423a-96b7-2d4756ec77d1"
resource_id_2025 = "c88d04a6-fe42-413b-b7bf-86e390494fb0"

#base_url_2024 = f"https://dadosabertos.ccee.org.br/api/3/action/datastore_search?resource_id={resource_id_2024}"
base_url_2025 = f"https://dadosabertos.ccee.org.br/api/3/action/datastore_search?resource_id={resource_id_2025}"

@st.cache_data(show_spinner=False, func=None, persist='disk')
def carregar_dados(url, ano, max_requests=50, max_retries=5, max_empty_responses=3):
    all_records = []
    limit = 10000
    offset = 0
    request_count = 0
    empty_responses = 0
    
    with st.spinner(f"Carregando dados de {ano}..."):
        while request_count < max_requests:
            retries = 0
            while retries < max_retries:
                try:
                    response = requests.get(f"{url}&limit={limit}&offset={offset}", timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    records = data.get("result", {}).get("records", [])
                    
                    if not records:
                        empty_responses += 1
                        if empty_responses >= max_empty_responses:
                            break
                    else:
                        empty_responses = 0
                        all_records.extend(records)
                        offset += limit
                        request_count += 1
                    break
                except requests.exceptions.RequestException:
                    retries += 1
                    time.sleep(5)
            if empty_responses >= max_empty_responses:
                break

    df = pd.DataFrame(all_records)
    
    if "MES_REFERENCIA" in df.columns:
        df["MES_REFERENCIA"] = df["MES_REFERENCIA"].astype(str)
        df["MES_REFERENCIA"] = df["MES_REFERENCIA"].apply(lambda x: f"01/{x[4:6]}/{x[:4]}")
    
    return df

@st.cache_data(show_spinner=False, func=None, persist='disk')
def carregar_excel(nome_arquivo, ano):
    with st.spinner(f"Carregando dados de {ano}..."):
        df = pd.read_json(nome_arquivo, orient="split", compression="gzip")
    return df

# Status carregamento
df_2025 = carregar_dados(base_url_2025, 2025)
#df_2024_api = carregar_dados(base_url_2024, 2024)

# Remover abril/2024 dos dados da API (Está na base XLSX.)
#df_2024_api["MES_REFERENCIA"] = pd.to_datetime(df_2024_api["MES_REFERENCIA"], dayfirst=True, errors="coerce")
#df_2024_api = df_2024_api[df_2024_api["MES_REFERENCIA"].dt.month != 4]

df_xlsx_2024 = carregar_excel("base_de_dados_nacional_2024_final.json", 2024)
#df_2024 = pd.concat([df_xlsx_2024, df_2024_api], ignore_index=True)
df_xlsx_2023 = carregar_excel("base_de_dados_nacional_2023_split.json", 2023)
df_xlsx_2022 = carregar_excel("base_de_dados_nacional_2022_split.json", 2022)

# Consolidar tudo
df_total = pd.concat([df_xlsx_2022, df_xlsx_2023, df_xlsx_2024, df_2025], ignore_index=True)
df_total["MES_REFERENCIA"] = pd.to_datetime(df_total["MES_REFERENCIA"], format="%d/%m/%Y")
df_total_ord = df_total.sort_values(by="MES_REFERENCIA", ascending=False)

if "id" in df_total_ord.columns:
    df_total_ord = df_total_ord.drop(columns=["id"])

df_total_ord["HORAS_NO_MES"] = df_total_ord["MES_REFERENCIA"].apply(lambda x: monthrange(x.year, x.month)[1] * 24)

col_consumo = next((col for col in df_total_ord.columns if "CONSUMO" in col.upper() and "TOTAL" in col.upper()), None)
if col_consumo:
    df_total_ord["CONSUMO_MWm"] = pd.to_numeric(df_total_ord[col_consumo], errors="coerce") / df_total_ord["HORAS_NO_MES"]

mes_mais_antigo = df_total_ord["MES_REFERENCIA"].min().strftime("%m/%Y")
mes_mais_recente = df_total_ord["MES_REFERENCIA"].max().strftime("%m/%Y")
st.success(f"Base de Dados Atualizada ({mes_mais_antigo} até {mes_mais_recente})")

st.write(f"Base completa tem {df_total_ord.shape[0]} registros.")

# --- Inputs
empresas_disponiveis = sorted(df_total_ord["NOME_EMPRESARIAL"].unique())
empresas_selecionadas = st.multiselect(
    "Selecione as empresas desejadas",
    options=empresas_disponiveis,
    default=None,
    placeholder="Selecione as empresas desejadas"
)

data_inicio = st.date_input("Data inicial", value=pd.to_datetime("2022-01-01"))
data_fim_default = df_total_ord["MES_REFERENCIA"].max().date()
data_fim = st.date_input("Data final", value=data_fim_default)

flex_user = st.slider("Flexibilidade (%)", min_value=1, max_value=100, value=30)

if st.button("Gerar Gráfico") and empresas_selecionadas:
    df_empresa = df_total_ord[df_total_ord["NOME_EMPRESARIAL"].isin(empresas_selecionadas)].copy()
    df_empresa = df_empresa[
        (df_empresa["MES_REFERENCIA"] >= pd.to_datetime(data_inicio)) &
        (df_empresa["MES_REFERENCIA"] <= pd.to_datetime(data_fim))
    ]
    df_empresa["Ano_Mes"] = df_empresa["MES_REFERENCIA"].dt.to_period("M")
    df_mensal = df_empresa.groupby("Ano_Mes")["CONSUMO_MWm"].sum().reset_index()
    df_mensal["Ano_Mes"] = df_mensal["Ano_Mes"].dt.to_timestamp(how="start")

    media_inicial = df_mensal["CONSUMO_MWm"].mean()
    flex_valor = media_inicial * (flex_user / 100)
    lim_sup_user = media_inicial + flex_valor
    lim_inf_user = media_inicial - flex_valor

    df_mensal["fora_faixa"] = ~df_mensal["CONSUMO_MWm"].between(lim_inf_user, lim_sup_user)
    media_consumo_ajustada = df_mensal.loc[~df_mensal["fora_faixa"], "CONSUMO_MWm"].mean()

    flex_valor = media_consumo_ajustada * (flex_user / 100)
    lim_sup_user = media_consumo_ajustada + flex_valor
    lim_inf_user = media_consumo_ajustada - flex_valor

    df_mensal["fora_faixa"] = ~df_mensal["CONSUMO_MWm"].between(lim_inf_user, lim_sup_user)

    fig = go.Figure()

    cores_barras = np.where(df_mensal["fora_faixa"], "crimson", "royalblue")

    fig.add_trace(go.Bar(
        x=df_mensal["Ano_Mes"],
        y=df_mensal["CONSUMO_MWm"],
        name="Consumo Mensal (MWm)",
        marker_color=cores_barras,
        hovertemplate="Mês: %{x|%b-%Y}<br>Consumo: %{y:.2f} MWm<extra></extra>"
    ))

    fig.add_trace(go.Scatter(
        x=df_mensal["Ano_Mes"],
        y=[media_consumo_ajustada]*len(df_mensal),
        mode="lines",
        name=f"Média: {media_consumo_ajustada:.2f}",
        line=dict(color="green", dash="dash")
    ))

    fig.add_trace(go.Scatter(
        x=df_mensal["Ano_Mes"],
        y=[lim_sup_user]*len(df_mensal),
        mode="lines",
        name=f"Limite Superior (+{flex_user}%): {lim_sup_user:.2f}",
        line=dict(color="orange", dash="dot")
    ))

    fig.add_trace(go.Scatter(
        x=df_mensal["Ano_Mes"],
        y=[lim_inf_user]*len(df_mensal),
        mode="lines",
        name=f"Limite Inferior (-{flex_user}%): {lim_inf_user:.2f}",
        line=dict(color="orange", dash="dot")
    ))

    # Linhas verticais entre os anos
    anos = df_mensal["Ano_Mes"].dt.year.unique()
    linhas_verticais = []
    for ano in anos[:-1]:
        dezembro = pd.Timestamp(f"{ano}-12-15")
        janeiro = pd.Timestamp(f"{ano+1}-01-15")
        meio = dezembro + (janeiro - dezembro) / 2
        linhas_verticais.append(
                dict(
                    type="line",
                    x0=meio,
                    x1=meio,
                    y0=0,
                    y1=1.02,
                    xref="x",
                    yref="paper",
                    line=dict(color="gray", width=5, dash="dot"),
                    layer="below"
                )
            )
    fig.update_layout(shapes=linhas_verticais)

    fig.update_layout(
        title=f"Histórico de Consumo Mensal - {' + '.join(empresas_selecionadas)}",
        xaxis_title="Mês",
        yaxis_title="Consumo (MWm)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        hovermode="x unified",
        height=500,
        yaxis=dict(showgrid=False)
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- Comparação de crescimento ano a ano ---
    df_mensal["Ano"] = df_mensal["Ano_Mes"].dt.year
    media_anuais = df_mensal.groupby("Ano")["CONSUMO_MWm"].mean().reset_index()
    media_anuais.columns = ["Ano", "Média Mensal de Consumo (MWm)"]

    media_anuais["Variação (%)"] = media_anuais["Média Mensal de Consumo (MWm)"].pct_change() * 100

    st.subheader("📈 Crescimento Anual do Consumo")
    #st.dataframe(
    #    media_anuais.style.format({
    #        "Média Mensal de Consumo (MWm)": "{:.2f}",
    #        "Variação (%)": "{:+.2f} %"
    #    }),
    #    use_container_width=False,
    #    hide_index=True
    #)
    
    # Filtrar empresas selecionadas
    if empresas_selecionadas:
        df_total_ord = df_total_ord[df_total_ord["NOME_EMPRESARIAL"].isin(empresas_selecionadas)].copy()
    else:
        st.warning("Por favor, selecione ao menos uma empresa.")
        st.stop()
    
    # 🔹 Filtrar os últimos 12 meses
    data_limite = df_total_ord["MES_REFERENCIA"].max() - pd.DateOffset(months=12)
    df_ultimos_12_meses = df_total_ord[df_total_ord["MES_REFERENCIA"] >= data_limite]

    # 🔹 Contar Unidades únicas
    unidades_unicas = df_ultimos_12_meses["SIGLA_PARCELA_CARGA"].nunique()

    # 🔹 Verificar Submercado misto
    submercado_misto = "Sim" if df_ultimos_12_meses["SUBMERCADO"].nunique() > 1 else "Não"

    # 🔹 Formatar CNPJ
    def format_cnpj(cnpj):
        try:
            if pd.isna(cnpj) or str(cnpj).strip() == '':
                return ''
            cnpj = str(int(float(cnpj))).zfill(14)
            return re.sub(r'(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})', r'\1.\2.\3/\4-\5', cnpj)
        except (ValueError, TypeError):
            return ''

    df_ultimos_12_meses["CNPJ_CARGA"] = df_ultimos_12_meses["CNPJ_CARGA"].apply(format_cnpj)

    # 🔹 Determinar o centro decisório
    definir_centro = df_ultimos_12_meses.copy()
    definir_centro["MATRIZ"] = definir_centro["CNPJ_CARGA"].apply(lambda x: x[11:15] == "0001")

    consumo_por_cnpj = definir_centro.groupby("CNPJ_CARGA")["CONSUMO_MWm"].mean().reset_index()
    definir_centro = definir_centro.merge(consumo_por_cnpj, on="CNPJ_CARGA", suffixes=("", "_MEDIO"))

    if definir_centro["MATRIZ"].any():
        centro_decisorio = definir_centro[definir_centro["MATRIZ"]][["CIDADE", "ESTADO_UF", "CNPJ_CARGA"]].iloc[0]
    else:
        idx_maior_consumo = definir_centro["CONSUMO_MWm_MEDIO"].idxmax()
        centro_decisorio = definir_centro.loc[idx_maior_consumo, ["CIDADE", "ESTADO_UF", "CNPJ_CARGA"]]

    resumo_dados = []

    for empresa in empresas_selecionadas:
        df_emp = df_total_ord[df_total_ord["NOME_EMPRESARIAL"] == empresa].copy()
        df_emp_12m = df_emp[df_emp["MES_REFERENCIA"] >= data_limite].copy()

        unidades = df_emp_12m["SIGLA_PARCELA_CARGA"].nunique()
        sub_misto = "Sim" if df_emp_12m["SUBMERCADO"].nunique() > 1 else "Não"

        # Definir centro decisório
        df_emp_12m["CNPJ_CARGA"] = df_emp_12m["CNPJ_CARGA"].apply(format_cnpj)
        definir_centro = df_emp_12m.copy()
        definir_centro["MATRIZ"] = definir_centro["CNPJ_CARGA"].apply(lambda x: x[11:15] == "0001")
        consumo_por_cnpj = definir_centro.groupby("CNPJ_CARGA")["CONSUMO_MWm"].mean().reset_index()
        definir_centro = definir_centro.merge(consumo_por_cnpj, on="CNPJ_CARGA", suffixes=("", "_MEDIO"))

        if definir_centro["MATRIZ"].any():
            centro = definir_centro[definir_centro["MATRIZ"]][["CIDADE", "ESTADO_UF", "CNPJ_CARGA"]].iloc[0]
        else:
            idx_maior_consumo = definir_centro["CONSUMO_MWm_MEDIO"].idxmax()
            centro = definir_centro.loc[idx_maior_consumo, ["CIDADE", "ESTADO_UF", "CNPJ_CARGA"]]

        resumo_dados.append({
            "Empresa": empresa,
            "Unidades": unidades,
            "Submercado Misto": sub_misto,
            "Possível Centro Decisório": f"{centro['CIDADE']} / {centro['ESTADO_UF']}",
            "CNPJ do Centro Decisório": centro["CNPJ_CARGA"]
        })

    resumo_df = pd.DataFrame(resumo_dados)
    st.write("### 📋 Resumo da(s) Empresa(s)")
    st.dataframe(resumo_df, hide_index=True)

    # 🔹 Tabela de percentual de consumo por submercado
    if not df_ultimos_12_meses.empty:
        consumo_por_sub = df_ultimos_12_meses.groupby("SUBMERCADO").agg({
            "CONSUMO_MWm": "sum",
            "SIGLA_PARCELA_CARGA": pd.Series.nunique
        }).reset_index()

        consumo_por_sub.rename(columns={"SIGLA_PARCELA_CARGA": "Unidades"}, inplace=True)
        total_consumo = consumo_por_sub["CONSUMO_MWm"].sum()
        consumo_por_sub["Consumo Médio Mensal (MWm)"] = consumo_por_sub["CONSUMO_MWm"] / 12

        if total_consumo > 0:
            consumo_por_sub["% do Total"] = (consumo_por_sub["CONSUMO_MWm"] / total_consumo) * 100
        else:
            consumo_por_sub["% do Total"] = 0

        consumo_por_sub["% do Total"] = consumo_por_sub["% do Total"].map("{:.2f}%".format)
        consumo_por_sub = consumo_por_sub.drop(columns=["CONSUMO_MWm"])

        st.write("### 🌎 Percentual de Consumo por Submercado")
        st.dataframe(consumo_por_sub, hide_index=True)


    # 🔹 Detalhamento por unidade
    dados_unidades = []
    unidades = df_ultimos_12_meses["SIGLA_PARCELA_CARGA"].unique()

    for unidade in unidades:
        df_unidade = df_ultimos_12_meses[df_ultimos_12_meses["SIGLA_PARCELA_CARGA"] == unidade]
        cnpj = df_unidade["CNPJ_CARGA"].iloc[0]
        cidade = df_unidade["CIDADE"].iloc[0]
        estado = df_unidade["ESTADO_UF"].iloc[0]
        submercado = df_unidade["SUBMERCADO"].iloc[0]
        capacidade = df_unidade["CAPACIDADE_CARGA"].iloc[0]
        consumo_12m = df_unidade["CONSUMO_MWm"].mean()

        dados_unidades.append({
            "Unidade": unidade,
            "CNPJ": cnpj,
            "Cidade": cidade,
            "Estado": estado,
            "Submercado": submercado,
            "Demanda": capacidade,
            "Consumo 12m (MWm)": round(consumo_12m, 2)
        })

    tabela_unidades = pd.DataFrame(dados_unidades)

    st.write("### 🏭 Detalhamento por Unidade")
    st.dataframe(tabela_unidades, hide_index=True)
