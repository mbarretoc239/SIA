import os
import sys

# ==========================================
# CONSTANTES DE DADOS EMBUTIDOS
# ==========================================
CLASSIFICACAO_GLOSAS_PADRAO = """Glosa;DESCRIÇÃO;TIPO DE GLOSA;NÍVEL;SUB GL0SA;DESCRIÇÃO SUB GLOSA
2;SOLICITANTE NAO ESTA CADASTRADO;Administrativa;Aviso;;
4;FALTA DATA DE ATENDIMENTO;Administrativa;Normal;;
5;PRESTADOR NAO ESTA CADASTRADO;Administrativa;Normal;;
8;USUARIO NAO ESTA CADASTRADO;Administrativa;Normal;;
9;FALTA CODIGO DO USUARIO;Administrativa;Normal;;
10;USUARIO NAO ATIVO;Administrativa;Normal;;
12;USUARIO CUMPRINDO CARENCIA;Administrativa;Normal;;
13;DATA DE ATENDIMENTO POSTERIOR AO PERÍODO ANALISADO;Administrativa;Normal;;
14;PROCEDIMENTO NAO AUTORIZADO/AUDITADO;Administrativa;Normal;;
16;GUIA DIGITADA SEM ITENS DE SERVICO;Administrativa;Normal;;
17;CODIGO PROCEDIMENTO NAO EXISTE;Administrativa;Normal;;
18;CODIGO A.M.B NAO INFORMADO;Administrativa;Normal;;
23;PRESTADOR N/CRED. NESTE SERVICO;Administrativa;Normal;;
25;IDADE FORA LIMITE PERMITIDO P/PROCEDIMENTO;Administrativa;Aviso;;
27;DUPLICIDADE DE COBRANCA;Administrativa;Normal;;
30;PREST. NAO CRED. NO SERV/ REDE DO USUARIO;Administrativa;Normal;;
31;QUANTIDADE COBRADA MAIOR QUE A AUTORIZADA;Administrativa;Normal;;
32;QUANTIDADE PAGA MAIOR QUE A AUTORIZADA;Administrativa;Normal;;
34;PROCEDIMENTO AUTORIZADO P/ OUTRO CREDENCIADO;Administrativa;Normal;;
35;PROCEDIMENTO AUTORIZADO PARA OUTRO USUARIO;Administrativa;Normal;;
36;QUANTIDADE A PAGAR MAIOR QUE A COBRADA;Administrativa;Normal;;
37;VALOR A PAGAR MAIOR QUE O COBRADA;Administrativa;Normal;;
38;QUANTIDADE A PAGAR MENOR QUE A COBRADA;Administrativa;Aviso;;
39;VALOR A PAGAR MENOR QUE O COBRADO;Administrativa;Aviso;;
40;PROCEDIMENTO NAO COBERTO PELO HAPVIDA;Administrativa;Normal;;
41;PRESTADOR CANCE NA REALIZACAO PROCEDIMENTO;Administrativa;Normal;;
42;PRESTADOR NAO E UM CREDENCIADO;Administrativa;Normal;;
43;PRAZO DE APRESENTAÇÃO VENCIDO;Administrativa;Normal;;
44;AUTORIZACAO NAO EXISTE OU CANCELADA;Administrativa;Normal;;
45;PROCEDIMENTO NAO COBERTO PELO PLANO;Administrativa;Normal;;
50;PROCEDIMENTO NAO AUTORIZADO;Administrativa;Normal;;
51;ITEM DA AUTORIZACAO COM STATUS PEDENTE;Administrativa;Normal;;
52;PROCEDIMENTO NEGADO;Administrativa;Normal;;
60;PRESTADOR NAO CADASTRADO NESTA ESPECIALIDADE;Administrativa;Normal;;
63;AUTORIZACAO PENDENTE;Administrativa;Normal;;
65;USUARIO INADIMPLENTE;Administrativa;Normal;;
66;PROCEDIMENTO PRESTADOR N/REALIZA;Administrativa;Normal;;
67;GUIA INCOMPATIVEL COM GUIA DA AUTORIZACAO;Administrativa;Normal;;
68;PRESTADOR ULTRAPASSOU LIMITE DE PROCEDIMENTO;Administrativa;Normal;;
69;EXCEDEU O MÁXIMO DE PROCEDIMENTO POR USUÁRIO;Administrativa;Normal;;
70;PROCEDIMENTO CANCELADO PELO PRESTADOR/NÃO EXECUTADO NA VALIDADE;Administrativa;Normal;;
71;VALOR TOTAL DIFERE VALOR APRESENTADO;Administrativa;Normal;;
72;VALOR APRESENTADO ACIMA DO TETO;Administrativa;Normal;;
74;PROCEDIMENTO NAO EXECUTADO EM SISTEMA;Administrativa;Normal;;
401;FALTA ASSINATURA DO USUARIO/'RESPONSAVEL;Administrativa;Normal;1;Falta assinatura do usuário na prescrição
401;FALTA ASSINATURA DO USUARIO/'RESPONSAVEL;Administrativa;Normal;2;Falta assinatura do usuário/responsável no laudo
402;RASURA NA DATA DE ATENDIMENTO;Administrativa;Normal;;
403;RASURA ASSINATURA DO ASSOCIADO;Administrativa;Normal;;
404;FALTA CARIMBO/ASSINATURA DO CREDENCIADO;Administrativa;Normal;1;Falta carimbo/assinatura do profissional na prescrição medicamentosa
404;FALTA CARIMBO/ASSINATURA DO CREDENCIADO;Administrativa;Normal;2;Falta carimbo/assinatura do profissional no laudo
405;FALTA DATA DO ATENDIMENTO;Administrativa;Normal;;
406;COBRANÇA EM DUPLICIDADE;Administrativa;Normal;;
407;PROCEDIMENTO SEM COBERTURA;Administrativa;Normal;;
408;CRED ULTRAPASSOU O LIMITE DE PROCEDIMENTO;Administrativa;Normal;;
409;PRESTADOR NAO CREDENCIADO PARA ESTE SERVICO;Administrativa;Normal;;
410;FALTA RX;Administrativa;Normal;2;Levantamento radiográfico não enviado
410;FALTA RX;Administrativa;Normal;3;Radiografia Panorâmica não enviada
410;FALTA RX;Administrativa;Normal;1;Tomografia não enviada
411;PROC. FORA DE PADRÃO TÉCNICO - REAVALIAR;Técnica;Normal;;
412;PROC. FORA DO PADRÃO DE QUALIDADE;Técnica;Normal;;
413;PROCEDIMENTO NÃO CONFIGURA URGÊNCIA;Técnica;Normal;;
414;RX APRESENTA FALHA TÉCNICA;Técnica;Normal;6;Incidência/posicionamento incorreto da tomada radiográfica
414;RX APRESENTA FALHA TÉCNICA;Técnica;Normal;1;Raio x inicial
414;RX APRESENTA FALHA TÉCNICA;Técnica;Normal;2;Raio x final
414;RX APRESENTA FALHA TÉCNICA;Técnica;Normal;3;Falha de processamento
414;RX APRESENTA FALHA TÉCNICA;Técnica;Normal;4;Presença de halo
414;RX APRESENTA FALHA TÉCNICA;Técnica;Normal;5;Presença de ranhura
415;PROCEDIMENTO EM PERÍODO DE VALIDADE PARA O MESMO PRESTADOR;Administrativa;Normal;1;
416;USUARIO INADIMPLENTE;Administrativa;Normal;;
417;FALTA INFORMAR O ELEMENTO;Administrativa;Normal;;
418;PROCEDIMENTO CANCELADO PELO AUDITOR;Técnica;Normal;;
419;PROCEDIMENTO NÃO AUTORIZADO;Administrativa;Normal;;
420;FALTA RX FINAL;Administrativa;Normal;;
421;COBRANÇA DE PROCEDIMENTO SEM JUSTIFICATIVA OU COM JUSTIFICATIVA INSUFICIENTE;Técnica;Normal;1;Falta de evidência solicitada.
421;COBRANÇA DE PROCEDIMENTO SEM JUSTIFICATIVA OU COM JUSTIFICATIVA INSUFICIENTE;Técnica;Normal;2;Justificativa incompatível para a solicitação do procedimento.
421;COBRANÇA DE PROCEDIMENTO SEM JUSTIFICATIVA OU COM JUSTIFICATIVA INSUFICIENTE;Técnica;Normal;3;Falta diagnóstico
421;COBRANÇA DE PROCEDIMENTO SEM JUSTIFICATIVA OU COM JUSTIFICATIVA INSUFICIENTE;Técnica;Normal;4;Laudo enviado não confere com histórico de atendimento
421;COBRANÇA DE PROCEDIMENTO SEM JUSTIFICATIVA OU COM JUSTIFICATIVA INSUFICIENTE;Técnica;Normal;5;Não enviado descrição/localização/sugestão diagnóstica
422;PROCEDIMENTO ILEGIVEL;Administrativa;Normal;2;Laudo ilegível
422;PROCEDIMENTO ILEGIVEL;Administrativa;Normal;1;Detalhamento do procedimento em guia física ilegível.
423;RADIOGRAFIA NÃO EVIDENCIA CAPEAMENTO;Técnica;Normal;;
424;CONTRATO ODONTOLOGICO NÃO INICIADO;Administrativa;Normal;;
425;PROCEDIMENTO INCOMPATIVEL COM A IDADE;Técnica;Normal;;
426;USUARIO EM PERIODO DE CARENCIA;Administrativa;Normal;;
427;USUARIO INADIMPLENTE;Administrativa;Normal;;
428;PROCEDIMENTO EM ANALISE PELA AUDITORIA;Técnica;Normal;;
429;USUARIO SEM COBERTURA ODONTOLOGICA;Administrativa;Normal;;
430;FALTA RX INICIAL;Administrativa;Normal;1;Raio x enviado como inicial evidencia prova do cone
431;PACIENTE CANCELOU O PLANO ODONTOLOGICO;Administrativa;Normal;;
432;DATA ATEND. POSTERIOR AO PERIODO ANALISADO;Administrativa;Normal;;
433;PROCEDIMENTO FALHOU NO PRAZO DE VALIDADE;Técnica;Normal;;
434;PROCEDIMENTO NÃO AUTORIZADO PARA ESTA GUIA;Administrativa;Normal;;
435;TRATAMENTO ENDODÔNTICO REALIZADO ANTERIORMENT;Técnica;Normal;;
436;RAIO X NÃO CORRESPONDE AO ELEMENTO REFERIDO;Técnica;Normal;1;Imagem não corresponde ao dente solicitado
436;RAIO X NÃO CORRESPONDE AO ELEMENTO REFERIDO;Técnica;Normal;2;Imagem não corresponde a região solicitada
437;RX FINAL NÃO CORRESPONDE AO INICIAL;Técnica;Normal;;
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;23;Raio x final sugere desobturação excessiva do conduto.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;24;Requisição sem identificação do usuário
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;28;Solicitação inclusa no procedimento protético
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;31;Rx sugere necessidade de tratamento endodôntico prévio
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;1;Usuário em tratamento pelo mesmo prestador.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;2;Panorâmica sem identificação
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;3;Imagem evidencia preparo prévio
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;4;Imagem evidencia finalidade estética
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;5;Imagem final evidencia procedimento realizado inadequadamente
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;6;Não envio de encaminhamento profissional Ortodontista ou Protesista solicitante
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;7;Não envio da solicitação do profissional Ortodontista solicitante
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;8;Raio X não adequado para análise do procedimento
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;9;Procedimento anterior relacionado apresenta falhas
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;10;Procedimento coberto apenas para dentes anteriores.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;16;Laudo sem assinatura do responsável.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;22;Procedimento não consta na solicitação do dentista assistente associado
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;27;Falta assinatura do credenciado na prescrição/laudo
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;11;Não envio da requisição do profissional solicitante.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;14;Imagem enviada para cobrança fora dos padrões técnicos
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;17;Falta descrever procedimento realizado.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;18;Falta prescrição
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;19;Falta assinatura do usuário na prescrição
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;30;Raio x evidencia núcleo/pino com desvio de conduto
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;15;Falta documentação/declaração da usuária.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;20;Não envio de periograma, índice de sangramento e/ou índice de placa.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;21;Não envio de periograma
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;25;Imagem enviada para cobrança fora dos padrões técnicos
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;29;Raio x final sugere lesão de furca
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;26;Raio x incluso no procedimento
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;12;Raio x final sugere Pino/Núcleo pré fabricado curto.
438;PROCEDIMENTO NÃO CORRESPONDE AS NORMAS TÉCNIC;Técnica;Normal;13;Raio x final evidencia Núcleo curto.
439;AUDITORIA SOLICITA GTO ORIGINAL;Administrativa;Normal;1;Procedimento não consta na guia física
440;ABERTURA DE CANAL REALIZADA ANTERIORMENTE;Técnica;Normal;;
441;REAVALIAR - PROSERVAR POR 60 DIAS;Técnica;Normal;;
442;GTO REENVIADA, PROCEDIMENTOS JA COBRADOS;Administrativa;Normal;;
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;15;Raio x  não evidencia indicação de reabilitação protética.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;16;Raio x evidencia dente anterior.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;23;Raio x evidencia tratamento endodôntico já realizado.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;1;Raio x incompatível com a descrição do procedimento.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;2;Raio x evidencia indicação de exodontia
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;4;Raio x evidencia dente hígido.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;5;Raio x evidencia dente permanente.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;6;Raio x evidencia tratamento endodôntico já realizado.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;7;Raio x inicial não evidencia tratamento endodôntico.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;8;Raio x inicial evidencia dente posterior.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;9;Raio x inicial evidencia ausência de núcleo intrarradicular.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;10;Raio x inicial evidencia indicação de endodontia.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;11;Raio x inicial evidencia acesso endodôntico prévio.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;12;Raio x evidencia dente com rizogênse completa.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;13;Raio x inicial evidencia dente decíduo.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;14;Raio x inicial não evidencia perda óssea.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;17;Raio x evidencia dente com indicação de restauração direta.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;18;Raio x evidencia dente sem tratamento endodôntico prévio.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;20;Raio x inicial evidencia procedimento diferente do solicitado.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;21;Raio x evidencia dente hígido.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;22;Raio x evidencia indicação de reabilitação protética.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;25;Raio x evidencia dente ausente.
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;26;Raio x sugere lesão de furca
443;RX NAO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;24;Raio x inicial não evidencia perda óssea compatível com doença periodontal ativa
444;ASSINATURA NÃO CONFERE;Administrativa;Normal;;
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;1;Raio x final não evidencia a obturação do(s) conduto(s).
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;19;Raio x final não evidencia remoção de tecido ósseo
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;27;Raio x inicial não evidencia a obturação do(s) conduto(s).
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;18;Raio x evidencia dente ausente.
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;20;Raio x final não evidencia dente/região por completo
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;29;Raio x final evidencia procedimento diferente do solicitado
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;2;Raio x final evidencia dente decíduo
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;3;Raio x final evidencia dente permanente
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;4;Raio x inicial não evidencia quantidade de face(s) solicitada(s).
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;5;Raio x evidencia indicação de restauração indireta.
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;7;Raio x final difere do inicial
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;8;Raio x final não evidencia selamento da perfuração
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;9;Raio x evidencia dente com ápice fechado
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;10;Raio x final evidencia falta de material intra-canal
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;11;Raio x final não evidencia material solcitado/autorizado
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;12;Raio x final não evidencia dente birradiculares
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;13;Raio x final evidencia condutos obturados
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;14;Raio x final não evidencia dente multirradicular
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;15;Raio x final não evidencia dente unirradicular
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;16;Raio x evidencia dente erupcionado
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;17;Raio x final não evidencia botão ortodôntico.
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;21;Imagem incompatível com diagnóstico/Descrição do procedimento
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;22;Imagem não evidencia necessidade de urgência
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;24;Raio x final não difere do inicial
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;25;Raio x evidencia faces diferentes
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;26;Raio x não permite análise do procedimento.
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;23;Imagem não corresponde ao dente solicitado
445;RX NÃO EVIDENCIA O PROCEDIMENTO SOLICITADO;Técnica;Normal;28;Rx Inicial Evidencia Procedimento Diferente Do Solicitado
446;FOTOGRAFIA NÃO ENVIADA;Administrativa;Normal;1;Fotografia inicial
446;FOTOGRAFIA NÃO ENVIADA;Administrativa;Normal;2;Fotografia final
446;FOTOGRAFIA NÃO ENVIADA;Administrativa;Normal;3;Fotografia anexada anteriormente à solicitação
446;FOTOGRAFIA NÃO ENVIADA;Administrativa;Normal;4;Fotografia anexada posteriormente à solicitação
447;RX EVIDENCIA CONDUTO SUB-OBTURADO;Técnica;Normal;;
448;RX EVIDENCIA CONDUTO COM FALHAS NA OBTURAÇÃO;Técnica;Normal;2;Falta de material obturador
448;RX EVIDENCIA CONDUTO COM FALHAS NA OBTURAÇÃO;Técnica;Normal;5;Raio x sugere desvio do conduto
448;RX EVIDENCIA CONDUTO COM FALHAS NA OBTURAÇÃO;Técnica;Normal;3;Raio x sugere perfuração
448;RX EVIDENCIA CONDUTO COM FALHAS NA OBTURAÇÃO;Técnica;Normal;6;Raio x final não evidencia a obturação de um ou mais condutos
448;RX EVIDENCIA CONDUTO COM FALHAS NA OBTURAÇÃO;Técnica;Normal;4;Raio x sugere desvio apical
448;RX EVIDENCIA CONDUTO COM FALHAS NA OBTURAÇÃO;Técnica;Normal;1;Conduto(s) sobreobturado(s)
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;6;Fotografia evidencia face(s) sem necessidade de intervenção
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;7;Fotografia inicial evidencia procedimento diferente do solicitado
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;8;Fotografia evidencia indicação de reabilitação protética.
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;1;Fotografia evidencia dente hígido
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;2;Fotografia evidencia indicação de exodontia
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;3;Fotografia evidencia indicação de tratamento endodôntico
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;4;Fotografia evidencia dente ausente
449;FOTOGRAFIA NÃO EVIDENCIA INDICAÇÃO DO PROCEDIMENTO;Técnica;Normal;5;Fotografia evidencia indicação de reabilitação protética
450;PROCEDIMENTO NÃO CONFERE COM O HISTÓRICO;Administrativa;Normal;2;Idade não confere com as imagens
450;PROCEDIMENTO NÃO CONFERE COM O HISTÓRICO;Administrativa;Normal;1;Procedimento não confere com histórico de atendimento
451;DATA DA VALIDADE DA GTO EXPIROU;Administrativa;Normal;;
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;6;Fotografia inicial não evidencia dente nitidamente
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;7;Fotografia inicial não evidencia região/sextante nitidamente
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;10;Fotografia inicial não permite análise do procedimento.
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;9;Fotografia não corresponde à região solicitada
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;1;Fotografia não evidencia quantidade de face(s) solicitada(s).
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;4;Fotografia final não permite análise do procedimento.
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;3;Fotografia evidencia face(s) diferente(s)
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;8;Fotografia evidencia dente ausente.
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;5;Fotografia não evidencia face(s) solicitada(s)
452;FOTOGRAFIA NÃO EVIDENCIA O PROCEDIMENTO;Técnica;Normal;2;Fotografia não evidencia dente solicitado
453;COBRANÇA FORA DO PRAZO DE VALIDADE;Administrativa;Normal;;
454;PROCEDIMENTO AUTORIZADO PARA OUTRO CREDENCIADO;Administrativa;Normal;1;Imagem repassada para outro prestador
456;AUSÊNCIA DE LAUDO TÉCNICO OU RESULTADO;Técnica;Normal;2;Ausência de laudo
456;AUSÊNCIA DE LAUDO TÉCNICO OU RESULTADO;Técnica;Normal;1;Ausência de laudo médico
457;FOTOGRAFIA DE MÁ QUALIDADE;Técnica;Normal;1;Fotografia inicial
457;FOTOGRAFIA DE MÁ QUALIDADE;Técnica;Normal;2;Fotografia final
457;FOTOGRAFIA DE MÁ QUALIDADE;Técnica;Normal;3;Fotografia com iluminação inadequada
457;FOTOGRAFIA DE MÁ QUALIDADE;Técnica;Normal;4;Fotografia com nitidez inadequada
457;FOTOGRAFIA DE MÁ QUALIDADE;Técnica;Normal;5;Imagem enviada sugere região contralateral
458;PRAZO DE APRESENTAÇÃO VENCIDO;Administrativa;Normal;;
459;IMAGEM SUGESTIVA DE MÁ ADAPTAÇÃO;Técnica;Normal;1;Sobrecontorno
459;IMAGEM SUGESTIVA DE MÁ ADAPTAÇÃO;Técnica;Normal;2;Falta de material reabilitador
459;IMAGEM SUGESTIVA DE MÁ ADAPTAÇÃO;Técnica;Normal;3;Falta de selamento entre remanescente dentário e material reabilitador/restaurador
459;IMAGEM SUGESTIVA DE MÁ ADAPTAÇÃO;Técnica;Normal;4;Falta de suporte à protese na câmara pulpar.
460;PROCEDIMENTO CANCELADO PELO SOLICITANTE APÓS AUTORIZAÇÃO;Administrativa;Normal;;
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;6;Procedimentos incompatíveis solicitados para o mesmo elemento
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;8;Não configura atendimento em horario conforme normas contratuais.
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;5;Relatório enviado indica necessidade especial
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;9;Solicitar todas as faces, contínuas ou não, no mesmo código
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;2;Raio x incluso no procedimento
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;1;Solicitação divergente da requisição/encaminhamento do profissional solicitante.
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;3;Usuário em tratamento com mesmo prestador
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;4;Imagem enviada não corresponde à região solicitada
461;COBRANÇA DE SOLICITAÇÃO INCORRETA;Administrativa;Normal;7;Procedimentos incompatíveis solicitados para o mesmo usuário
462;AUSÊNCIA DE TERMO DE CONSENTIMENTO/ TERMO DE ORIENTAÇÃO E CIÊNCIA;Administrativa;Normal;;
463;IMAGEM EM HISTÓRICO DE OUTRO BENEFICIÁRIO;Administrativa;Normal;;
464;TIPO GUIA INVÁLIDO;Administrativa;Normal;;
465;FOTOGRAFIA NÃO CORRESPONDE À REGIÃO SOLICITADA;Administrativa;Normal;;
466;IMAGEM NÃO CONFERE COM HISTÓRICO;Administrativa;Normal;;
467;PROCEDIMENTO SEM COLETA DE BIOMETRIA;Administrativa;Normal;;
468;EXCEDEU O MÁXIMO DE PROCEDIMENTO POR USUÁRIO;Administrativa;Normal;;
469;INFORMAÇÕES RELACIONADAS AO PROCEDIMENTO DIVERGENTES;Administrativa;Normal;1;Divergência entre a descrição do procedimento e/ou elemento informado no portal e guia física
469;INFORMAÇÕES RELACIONADAS AO PROCEDIMENTO DIVERGENTES;Administrativa;Normal;2;Divergência entre a descrição do procedimento e descrição em requisito
470;PROCEDIMENTO NÃO EXECUTADO;Administrativa;Normal;;
471;FALTA INFORMAR REGIÃO;Administrativa;Normal;;
472;FALTA REQUISITO;Administrativa;Normal;10;Documentação não anexada em sistema
472;FALTA REQUISITO;Administrativa;Normal;12;Falta laudo para procedimento
472;FALTA REQUISITO;Administrativa;Normal;9;Não envio de periograma
472;FALTA REQUISITO;Administrativa;Normal;1;Falta prescrição
472;FALTA REQUISITO;Administrativa;Normal;2;Falta encaminhamento do Ortodontista/Protesista
472;FALTA REQUISITO;Administrativa;Normal;3;Falta de solicitação do profissional Ortodontista
472;FALTA REQUISITO;Administrativa;Normal;4;Falta requisição do profissional solicitante
472;FALTA REQUISITO;Administrativa;Normal;5;Falta termo de consentimento livre e esclarecido/declaração do usuário
472;FALTA REQUISITO;Administrativa;Normal;8;Falta documentação/declaração da usuária
472;FALTA REQUISITO;Administrativa;Normal;6;Ausência de laudo médico/relatório
472;FALTA REQUISITO;Administrativa;Normal;7;Procedimento não consta na requisição/solicitação do profissional solicitante.
472;FALTA REQUISITO;Administrativa;Normal;11;Falta envio da Tomografia
473;DOCUMENTAÇÃO INCOMPLETA;Administrativa;Normal;3;Falta assinatura do usuário/responsável na prescrição
473;DOCUMENTAÇÃO INCOMPLETA;Administrativa;Normal;4;Falta Assinatura Do Usuário/Responsável No Laudo
473;DOCUMENTAÇÃO INCOMPLETA;Administrativa;Normal;5;Falta Carimbo/Assinatura Do Profissional Na Prescrição Medicamentosa
473;DOCUMENTAÇÃO INCOMPLETA;Administrativa;Normal;6;Falta Carimbo/Assinatura Do Profissional No Laudo/ Requisição
473;DOCUMENTAÇÃO INCOMPLETA;Administrativa;Normal;7;Prescrição sem identificação do usuário
473;DOCUMENTAÇÃO INCOMPLETA;Administrativa;Normal;1;Requisição/encaminhamento sem identificação do usuário
473;DOCUMENTAÇÃO INCOMPLETA;Administrativa;Normal;2;Requisição/encaminhamento sem identificação do profissional solicitante.
474;IMAGEM NÃO PERMITE ANÁLISE DO PROCEDIMENTO;Técnica;Normal;;
475;IMAGEM NÃO CORRESPONDE À REGIÃO/ELEMENTO REFERIDO;Técnica;Normal;5;Imagem enviada sugere região contralateral
475;IMAGEM NÃO CORRESPONDE À REGIÃO/ELEMENTO REFERIDO;Técnica;Normal;1;Raio x não corresponde ao dente solicitado
475;IMAGEM NÃO CORRESPONDE À REGIÃO/ELEMENTO REFERIDO;Técnica;Normal;2;Raio x não corresponde à região solicitada
475;IMAGEM NÃO CORRESPONDE À REGIÃO/ELEMENTO REFERIDO;Técnica;Normal;3;Fotografia não corresponde ao dente solicitado
475;IMAGEM NÃO CORRESPONDE À REGIÃO/ELEMENTO REFERIDO;Técnica;Normal;4;Fotografia não corresponde à região solicitada
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;7;Fotografia não evidencia elemento/face solicitada
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;8;Fotografia não evidencia dente/região por completo
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;1;Raio x final não evidencia dente/região por completo
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;2;Fotografia inicial não permite análise do procedimento
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;9;Raio x inicial não evidencia dente/região por completo
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;3;Não foi possível identificar região/elemento
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;4;Raio x final não permite análise do procedimento
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;5;Raio x inicial não permite análise do procedimento
476;IMAGEM INADEQUADA PARA ANÁLISE DO PROCEDIMENTO;Técnica;Normal;6;Fotografia final não permite análise do procedimento
477;PROCEDIMENTO EXECUTADO E NÃO ENVIADO PARA COBRANÇA;Administrativa;Normal;1;Não enviado GTo para cobrança
480;FALTA DOCUMENTAÇÃO;Administrativa;Normal;1;PROCEDIMENTO EXECUTADO E NÃO COBRADO - SEM ENVIO DE GUIA
481;PROCEDIMENTO EXECUTADO EM SISTEMA E NÃO REALIZADO;Administrativa;Normal;;
"""

# ==========================================
# TEMA VISUAL SIA v5
# ==========================================
TEMA = {
    "bg_app": "#081120",
    "bg_shell": "#0B1526",
    "bg_surface": "#0F1B2D",
    "bg_surface_2": "#13233A",
    "bg_surface_3": "#182C47",
    "bg_sidebar": "#0A1424",
    "bg_overlay": "#101B2E",

    "azul_primario": "#4F8CFF",
    "azul_secundario": "#3B76E6",
    "azul_hover": "#2F63C7",
    "azul_sidebar": "#11233D",
    "azul_sidebar_hover": "#1A3153",
    "azul_fundo": "#081120",
    "azul_fundo_escuro": "#050B15",

    "branco": "#F8FAFC",
    "branco_suave": "#D7E3F4",
    "branco_card": "#0F1B2D",

    "texto_claro": "#F8FAFC",
    "texto_escuro": "#E8EEF8",
    "texto_secundario": "#91A4C2",
    "texto_muted": "#6F84A5",

    "laranja": "#F59E0B",
    "laranja_hover": "#D98708",

    "erro": "#EF5350",
    "sucesso": "#22C55E",
    "aviso": "#38BDF8",
    "borda": "#223652",
    "borda_forte": "#2F4B70"
}

# Configurações de Banco de Dados
DB_NAME = "sia_auditoria.db"

# Funções auxiliares de configuração
def caminho_recurso(caminho_relativo):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(sys.argv[0]) or ".")
    return os.path.join(base_path, caminho_relativo)
