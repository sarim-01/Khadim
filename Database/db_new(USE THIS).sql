--
-- PostgreSQL database dump
--

-- Dumped from database version 18.1
-- Dumped by pg_dump version 18.1

-- Started on 2026-03-17 10:33:47

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 7 (class 2615 OID 16689)
-- Name: auth; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA auth;


ALTER SCHEMA auth OWNER TO postgres;

--
-- TOC entry 9 (class 2615 OID 16691)
-- Name: chat; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA chat;


ALTER SCHEMA chat OWNER TO postgres;

--
-- TOC entry 8 (class 2615 OID 16690)
-- Name: orders; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA orders;


ALTER SCHEMA orders OWNER TO postgres;

--
-- TOC entry 2 (class 3079 OID 16614)
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- TOC entry 5340 (class 0 OID 0)
-- Dependencies: 2
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- TOC entry 299 (class 1255 OID 16729)
-- Name: set_updated_at(); Type: FUNCTION; Schema: auth; Owner: postgres
--

CREATE FUNCTION auth.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION auth.set_updated_at() OWNER TO postgres;

--
-- TOC entry 300 (class 1255 OID 16801)
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION public.set_updated_at() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 238 (class 1259 OID 16692)
-- Name: app_users; Type: TABLE; Schema: auth; Owner: postgres
--

CREATE TABLE auth.app_users (
    user_id uuid DEFAULT gen_random_uuid() NOT NULL,
    full_name text NOT NULL,
    email text,
    phone text,
    password_hash text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT app_users_email_or_phone_chk CHECK (((email IS NOT NULL) OR (phone IS NOT NULL)))
);


ALTER TABLE auth.app_users OWNER TO postgres;

--
-- TOC entry 239 (class 1259 OID 16712)
-- Name: user_preferences; Type: TABLE; Schema: auth; Owner: postgres
--

CREATE TABLE auth.user_preferences (
    user_id uuid NOT NULL,
    preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE auth.user_preferences OWNER TO postgres;

--
-- TOC entry 249 (class 1259 OID 16939)
-- Name: messages; Type: TABLE; Schema: chat; Owner: postgres
--

CREATE TABLE chat.messages (
    message_id integer NOT NULL,
    session_id integer NOT NULL,
    user_id uuid,
    role character varying(20) NOT NULL,
    message_text text NOT NULL,
    message_type character varying(30) DEFAULT 'text'::character varying,
    tool_name character varying(100),
    tool_payload jsonb,
    tokens_used integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    metadata jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT messages_role_chk CHECK (((role)::text = ANY ((ARRAY['user'::character varying, 'assistant'::character varying, 'system'::character varying, 'tool'::character varying])::text[])))
);


ALTER TABLE chat.messages OWNER TO postgres;

--
-- TOC entry 248 (class 1259 OID 16938)
-- Name: messages_message_id_seq; Type: SEQUENCE; Schema: chat; Owner: postgres
--

CREATE SEQUENCE chat.messages_message_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE chat.messages_message_id_seq OWNER TO postgres;

--
-- TOC entry 5341 (class 0 OID 0)
-- Dependencies: 248
-- Name: messages_message_id_seq; Type: SEQUENCE OWNED BY; Schema: chat; Owner: postgres
--

ALTER SEQUENCE chat.messages_message_id_seq OWNED BY chat.messages.message_id;


--
-- TOC entry 247 (class 1259 OID 16915)
-- Name: sessions; Type: TABLE; Schema: chat; Owner: postgres
--

CREATE TABLE chat.sessions (
    session_id integer NOT NULL,
    user_id uuid NOT NULL,
    session_title character varying(255),
    session_type character varying(50) DEFAULT 'text'::character varying,
    language character varying(20) DEFAULT 'en'::character varying,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_activity_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true,
    context_data jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE chat.sessions OWNER TO postgres;

--
-- TOC entry 246 (class 1259 OID 16914)
-- Name: sessions_session_id_seq; Type: SEQUENCE; Schema: chat; Owner: postgres
--

CREATE SEQUENCE chat.sessions_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE chat.sessions_session_id_seq OWNER TO postgres;

--
-- TOC entry 5342 (class 0 OID 0)
-- Dependencies: 246
-- Name: sessions_session_id_seq; Type: SEQUENCE OWNED BY; Schema: chat; Owner: postgres
--

ALTER SEQUENCE chat.sessions_session_id_seq OWNED BY chat.sessions.session_id;


--
-- TOC entry 259 (class 1259 OID 17162)
-- Name: tool_calls; Type: TABLE; Schema: chat; Owner: postgres
--

CREATE TABLE chat.tool_calls (
    tool_call_id integer NOT NULL,
    session_id integer NOT NULL,
    message_id integer,
    user_id uuid,
    tool_name character varying(100) NOT NULL,
    tool_input jsonb DEFAULT '{}'::jsonb,
    tool_output jsonb DEFAULT '{}'::jsonb,
    status character varying(30) DEFAULT 'success'::character varying,
    error_message text,
    execution_time_ms integer,
    called_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    metadata jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT tool_calls_status_chk CHECK (((status)::text = ANY ((ARRAY['success'::character varying, 'failed'::character varying, 'timeout'::character varying, 'partial'::character varying])::text[])))
);


ALTER TABLE chat.tool_calls OWNER TO postgres;

--
-- TOC entry 258 (class 1259 OID 17161)
-- Name: tool_calls_tool_call_id_seq; Type: SEQUENCE; Schema: chat; Owner: postgres
--

CREATE SEQUENCE chat.tool_calls_tool_call_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE chat.tool_calls_tool_call_id_seq OWNER TO postgres;

--
-- TOC entry 5343 (class 0 OID 0)
-- Dependencies: 258
-- Name: tool_calls_tool_call_id_seq; Type: SEQUENCE OWNED BY; Schema: chat; Owner: postgres
--

ALTER SEQUENCE chat.tool_calls_tool_call_id_seq OWNED BY chat.tool_calls.tool_call_id;


--
-- TOC entry 251 (class 1259 OID 16969)
-- Name: voice_interactions; Type: TABLE; Schema: chat; Owner: postgres
--

CREATE TABLE chat.voice_interactions (
    interaction_id integer NOT NULL,
    session_id integer NOT NULL,
    user_id uuid NOT NULL,
    input_audio_path text,
    input_transcript text,
    detected_language character varying(20),
    assistant_response_text text,
    output_audio_path text,
    stt_provider character varying(50),
    tts_provider character varying(50),
    processing_status character varying(30) DEFAULT 'completed'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    metadata jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE chat.voice_interactions OWNER TO postgres;

--
-- TOC entry 250 (class 1259 OID 16968)
-- Name: voice_interactions_interaction_id_seq; Type: SEQUENCE; Schema: chat; Owner: postgres
--

CREATE SEQUENCE chat.voice_interactions_interaction_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE chat.voice_interactions_interaction_id_seq OWNER TO postgres;

--
-- TOC entry 5344 (class 0 OID 0)
-- Dependencies: 250
-- Name: voice_interactions_interaction_id_seq; Type: SEQUENCE OWNED BY; Schema: chat; Owner: postgres
--

ALTER SEQUENCE chat.voice_interactions_interaction_id_seq OWNED BY chat.voice_interactions.interaction_id;


--
-- TOC entry 234 (class 1259 OID 16576)
-- Name: cart; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cart (
    cart_id uuid NOT NULL,
    status text DEFAULT 'active'::text,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    user_id uuid,
    CONSTRAINT cart_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'checking_out'::text, 'inactive'::text, 'abandoned'::text])))
);


ALTER TABLE public.cart OWNER TO postgres;

--
-- TOC entry 237 (class 1259 OID 16599)
-- Name: cart_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cart_items (
    cart_id uuid NOT NULL,
    item_id integer NOT NULL,
    item_type text NOT NULL,
    item_name text,
    quantity integer,
    unit_price numeric(10,2),
    CONSTRAINT cart_items_item_type_chk CHECK ((item_type = ANY (ARRAY['menu_item'::text, 'deal'::text])))
);


ALTER TABLE public.cart_items OWNER TO postgres;

--
-- TOC entry 224 (class 1259 OID 16474)
-- Name: chef; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chef (
    cheff_id integer NOT NULL,
    cheff_name text NOT NULL,
    specialty text,
    active_status boolean DEFAULT true,
    max_current_orders integer
);


ALTER TABLE public.chef OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 16473)
-- Name: chef_cheff_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chef_cheff_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chef_cheff_id_seq OWNER TO postgres;

--
-- TOC entry 5345 (class 0 OID 0)
-- Dependencies: 223
-- Name: chef_cheff_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chef_cheff_id_seq OWNED BY public.chef.cheff_id;


--
-- TOC entry 228 (class 1259 OID 16500)
-- Name: deal; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.deal (
    deal_id integer NOT NULL,
    deal_name text NOT NULL,
    deal_price numeric(7,2),
    active boolean DEFAULT true,
    serving_size integer,
    image_url text
);


ALTER TABLE public.deal OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 16499)
-- Name: deal_deal_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.deal_deal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.deal_deal_id_seq OWNER TO postgres;

--
-- TOC entry 5346 (class 0 OID 0)
-- Dependencies: 227
-- Name: deal_deal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.deal_deal_id_seq OWNED BY public.deal.deal_id;


--
-- TOC entry 229 (class 1259 OID 16511)
-- Name: deal_item; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.deal_item (
    deal_id integer NOT NULL,
    menu_item_id integer NOT NULL,
    quantity integer NOT NULL
);


ALTER TABLE public.deal_item OWNER TO postgres;

--
-- TOC entry 261 (class 1259 OID 17215)
-- Name: feedback; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.feedback (
    feedback_id integer NOT NULL,
    user_id uuid NOT NULL,
    order_id integer,
    rating integer NOT NULL,
    message text NOT NULL,
    feedback_type character varying(30) DEFAULT 'GENERAL'::character varying,
    status character varying(20) DEFAULT 'NEW'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT feedback_rating_check CHECK (((rating >= 1) AND (rating <= 5))),
    CONSTRAINT feedback_status_chk CHECK (((status)::text = ANY ((ARRAY['NEW'::character varying, 'REVIEWED'::character varying, 'RESOLVED'::character varying])::text[]))),
    CONSTRAINT feedback_type_chk CHECK (((feedback_type)::text = ANY ((ARRAY['GENERAL'::character varying, 'ORDER'::character varying, 'DELIVERY'::character varying, 'APP'::character varying, 'FOOD'::character varying])::text[])))
);


ALTER TABLE public.feedback OWNER TO postgres;

--
-- TOC entry 260 (class 1259 OID 17214)
-- Name: feedback_feedback_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.feedback_feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.feedback_feedback_id_seq OWNER TO postgres;

--
-- TOC entry 5347 (class 0 OID 0)
-- Dependencies: 260
-- Name: feedback_feedback_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.feedback_feedback_id_seq OWNED BY public.feedback.feedback_id;


--
-- TOC entry 257 (class 1259 OID 17122)
-- Name: kitchen_task_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.kitchen_task_history (
    history_id integer NOT NULL,
    task_id text NOT NULL,
    order_id integer NOT NULL,
    old_status character varying(50),
    new_status character varying(50) NOT NULL,
    old_cheff_id integer,
    new_cheff_id integer,
    changed_by character varying(50) DEFAULT 'system'::character varying,
    notes text,
    changed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    metadata jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE public.kitchen_task_history OWNER TO postgres;

--
-- TOC entry 256 (class 1259 OID 17121)
-- Name: kitchen_task_history_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.kitchen_task_history_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.kitchen_task_history_history_id_seq OWNER TO postgres;

--
-- TOC entry 5348 (class 0 OID 0)
-- Dependencies: 256
-- Name: kitchen_task_history_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.kitchen_task_history_history_id_seq OWNED BY public.kitchen_task_history.history_id;


--
-- TOC entry 231 (class 1259 OID 16546)
-- Name: kitchen_tasks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.kitchen_tasks (
    task_id text NOT NULL,
    order_id integer NOT NULL,
    menu_item_id integer,
    item_name text,
    qty integer,
    station text,
    assigned_chef text,
    estimated_minutes integer,
    status text DEFAULT 'QUEUED'::text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.kitchen_tasks OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 16486)
-- Name: menu_item; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.menu_item (
    item_id integer NOT NULL,
    item_name text NOT NULL,
    item_description text,
    item_category text,
    item_cuisine text,
    item_price numeric(7,2),
    item_cost numeric(7,2),
    tags text[],
    availability boolean DEFAULT true,
    serving_size integer,
    quantity_description text,
    prep_time_minutes integer,
    image_url text,
    CONSTRAINT menu_item_item_category_check CHECK ((item_category = ANY (ARRAY['starter'::text, 'main'::text, 'drink'::text, 'side'::text, 'bread'::text]))),
    CONSTRAINT menu_item_item_cuisine_check CHECK ((item_cuisine = ANY (ARRAY['BBQ'::text, 'Desi'::text, 'Fast Food'::text, 'Chinese'::text, 'Drinks'::text])))
);


ALTER TABLE public.menu_item OWNER TO postgres;

--
-- TOC entry 230 (class 1259 OID 16529)
-- Name: menu_item_chefs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.menu_item_chefs (
    menu_item_id integer NOT NULL,
    chef_id integer NOT NULL
);


ALTER TABLE public.menu_item_chefs OWNER TO postgres;

--
-- TOC entry 225 (class 1259 OID 16485)
-- Name: menu_item_item_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.menu_item_item_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_item_item_id_seq OWNER TO postgres;

--
-- TOC entry 5349 (class 0 OID 0)
-- Dependencies: 225
-- Name: menu_item_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.menu_item_item_id_seq OWNED BY public.menu_item.item_id;


--
-- TOC entry 233 (class 1259 OID 16562)
-- Name: offers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.offers (
    offer_id integer NOT NULL,
    title text NOT NULL,
    description text NOT NULL,
    offer_code text,
    validity date NOT NULL,
    category text NOT NULL,
    CONSTRAINT offers_category_check CHECK ((category = ANY (ARRAY['Fast Food'::text, 'Chinese'::text, 'Desi'::text, 'BBQ'::text, 'Drinks'::text])))
);


ALTER TABLE public.offers OWNER TO postgres;

--
-- TOC entry 232 (class 1259 OID 16561)
-- Name: offers_offer_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.offers_offer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.offers_offer_id_seq OWNER TO postgres;

--
-- TOC entry 5350 (class 0 OID 0)
-- Dependencies: 232
-- Name: offers_offer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.offers_offer_id_seq OWNED BY public.offers.offer_id;


--
-- TOC entry 255 (class 1259 OID 17018)
-- Name: order_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_events (
    event_id integer NOT NULL,
    order_id integer NOT NULL,
    event_type character varying(100) NOT NULL,
    event_source character varying(50) DEFAULT 'system'::character varying,
    event_data jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.order_events OWNER TO postgres;

--
-- TOC entry 254 (class 1259 OID 17017)
-- Name: order_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.order_events_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_events_event_id_seq OWNER TO postgres;

--
-- TOC entry 5351 (class 0 OID 0)
-- Dependencies: 254
-- Name: order_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.order_events_event_id_seq OWNED BY public.order_events.event_id;


--
-- TOC entry 241 (class 1259 OID 16768)
-- Name: order_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_items (
    id integer NOT NULL,
    order_id integer NOT NULL,
    item_type character varying(16) NOT NULL,
    item_id integer NOT NULL,
    name_snapshot text NOT NULL,
    unit_price_snapshot numeric(12,2) NOT NULL,
    quantity integer NOT NULL,
    line_total numeric(12,2) NOT NULL,
    CONSTRAINT order_items_item_type_chk CHECK (((item_type)::text = ANY ((ARRAY['menu_item'::character varying, 'deal'::character varying])::text[]))),
    CONSTRAINT order_items_quantity_check CHECK ((quantity > 0))
);


ALTER TABLE public.order_items OWNER TO postgres;

--
-- TOC entry 240 (class 1259 OID 16767)
-- Name: order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.order_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_items_id_seq OWNER TO postgres;

--
-- TOC entry 5352 (class 0 OID 0)
-- Dependencies: 240
-- Name: order_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.order_items_id_seq OWNED BY public.order_items.id;


--
-- TOC entry 253 (class 1259 OID 16997)
-- Name: order_status_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_status_history (
    id integer NOT NULL,
    order_id integer NOT NULL,
    old_status character varying(50),
    new_status character varying(50) NOT NULL,
    changed_by character varying(50) DEFAULT 'system'::character varying,
    notes text,
    changed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.order_status_history OWNER TO postgres;

--
-- TOC entry 252 (class 1259 OID 16996)
-- Name: order_status_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.order_status_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_status_history_id_seq OWNER TO postgres;

--
-- TOC entry 5353 (class 0 OID 0)
-- Dependencies: 252
-- Name: order_status_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.order_status_history_id_seq OWNED BY public.order_status_history.id;


--
-- TOC entry 236 (class 1259 OID 16581)
-- Name: orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.orders (
    order_id integer NOT NULL,
    cart_id uuid NOT NULL,
    total_price numeric(10,2) NOT NULL,
    estimated_prep_time_minutes integer,
    order_data jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    status text DEFAULT 'confirmed'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    delivery_address text,
    subtotal numeric(10,2),
    tax numeric(10,2),
    delivery_fee numeric(10,2),
    payment_method text,
    CONSTRAINT orders_status_chk CHECK ((lower(status) = ANY (ARRAY['created'::text, 'confirmed'::text, 'in_kitchen'::text, 'preparing'::text, 'ready'::text, 'completed'::text, 'cancelled'::text])))
);


ALTER TABLE public.orders OWNER TO postgres;

--
-- TOC entry 235 (class 1259 OID 16577)
-- Name: orders_order_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.orders_order_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.orders_order_id_seq OWNER TO postgres;

--
-- TOC entry 5354 (class 0 OID 0)
-- Dependencies: 235
-- Name: orders_order_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.orders_order_id_seq OWNED BY public.orders.order_id;


--
-- TOC entry 245 (class 1259 OID 16874)
-- Name: payments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.payments (
    id integer NOT NULL,
    transaction_id character varying NOT NULL,
    order_id integer,
    user_id uuid NOT NULL,
    card_id integer,
    amount numeric NOT NULL,
    card_last4 character varying,
    card_type character varying,
    cardholder_name character varying,
    status character varying DEFAULT 'PENDING'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    payment_method character varying(20) DEFAULT 'CARD'::character varying,
    CONSTRAINT payments_method_chk CHECK (((payment_method)::text = ANY ((ARRAY['CARD'::character varying, 'COD'::character varying])::text[])))
);


ALTER TABLE public.payments OWNER TO postgres;

--
-- TOC entry 244 (class 1259 OID 16873)
-- Name: payments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.payments_id_seq OWNER TO postgres;

--
-- TOC entry 5355 (class 0 OID 0)
-- Dependencies: 244
-- Name: payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.payments_id_seq OWNED BY public.payments.id;


--
-- TOC entry 243 (class 1259 OID 16859)
-- Name: saved_cards; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.saved_cards (
    card_id integer NOT NULL,
    user_id uuid NOT NULL,
    card_type character varying DEFAULT 'visa'::character varying,
    last4 character varying NOT NULL,
    cardholder_name character varying NOT NULL,
    expiry character varying NOT NULL,
    is_default boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.saved_cards OWNER TO postgres;

--
-- TOC entry 242 (class 1259 OID 16858)
-- Name: saved_cards_card_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.saved_cards_card_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.saved_cards_card_id_seq OWNER TO postgres;

--
-- TOC entry 5356 (class 0 OID 0)
-- Dependencies: 242
-- Name: saved_cards_card_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.saved_cards_card_id_seq OWNED BY public.saved_cards.card_id;


--
-- TOC entry 4992 (class 2604 OID 16942)
-- Name: messages message_id; Type: DEFAULT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.messages ALTER COLUMN message_id SET DEFAULT nextval('chat.messages_message_id_seq'::regclass);


--
-- TOC entry 4985 (class 2604 OID 16918)
-- Name: sessions session_id; Type: DEFAULT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.sessions ALTER COLUMN session_id SET DEFAULT nextval('chat.sessions_session_id_seq'::regclass);


--
-- TOC entry 5011 (class 2604 OID 17165)
-- Name: tool_calls tool_call_id; Type: DEFAULT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.tool_calls ALTER COLUMN tool_call_id SET DEFAULT nextval('chat.tool_calls_tool_call_id_seq'::regclass);


--
-- TOC entry 4996 (class 2604 OID 16972)
-- Name: voice_interactions interaction_id; Type: DEFAULT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.voice_interactions ALTER COLUMN interaction_id SET DEFAULT nextval('chat.voice_interactions_interaction_id_seq'::regclass);


--
-- TOC entry 4955 (class 2604 OID 16477)
-- Name: chef cheff_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chef ALTER COLUMN cheff_id SET DEFAULT nextval('public.chef_cheff_id_seq'::regclass);


--
-- TOC entry 4959 (class 2604 OID 16503)
-- Name: deal deal_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.deal ALTER COLUMN deal_id SET DEFAULT nextval('public.deal_deal_id_seq'::regclass);


--
-- TOC entry 5017 (class 2604 OID 17218)
-- Name: feedback feedback_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.feedback ALTER COLUMN feedback_id SET DEFAULT nextval('public.feedback_feedback_id_seq'::regclass);


--
-- TOC entry 5007 (class 2604 OID 17125)
-- Name: kitchen_task_history history_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kitchen_task_history ALTER COLUMN history_id SET DEFAULT nextval('public.kitchen_task_history_history_id_seq'::regclass);


--
-- TOC entry 4957 (class 2604 OID 16489)
-- Name: menu_item item_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.menu_item ALTER COLUMN item_id SET DEFAULT nextval('public.menu_item_item_id_seq'::regclass);


--
-- TOC entry 4964 (class 2604 OID 16565)
-- Name: offers offer_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.offers ALTER COLUMN offer_id SET DEFAULT nextval('public.offers_offer_id_seq'::regclass);


--
-- TOC entry 5003 (class 2604 OID 17021)
-- Name: order_events event_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_events ALTER COLUMN event_id SET DEFAULT nextval('public.order_events_event_id_seq'::regclass);


--
-- TOC entry 4976 (class 2604 OID 16771)
-- Name: order_items id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items ALTER COLUMN id SET DEFAULT nextval('public.order_items_id_seq'::regclass);


--
-- TOC entry 5000 (class 2604 OID 17000)
-- Name: order_status_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_status_history ALTER COLUMN id SET DEFAULT nextval('public.order_status_history_id_seq'::regclass);


--
-- TOC entry 4967 (class 2604 OID 16586)
-- Name: orders order_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders ALTER COLUMN order_id SET DEFAULT nextval('public.orders_order_id_seq'::regclass);


--
-- TOC entry 4981 (class 2604 OID 16877)
-- Name: payments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments ALTER COLUMN id SET DEFAULT nextval('public.payments_id_seq'::regclass);


--
-- TOC entry 4977 (class 2604 OID 16862)
-- Name: saved_cards card_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.saved_cards ALTER COLUMN card_id SET DEFAULT nextval('public.saved_cards_card_id_seq'::regclass);


--
-- TOC entry 5311 (class 0 OID 16692)
-- Dependencies: 238
-- Data for Name: app_users; Type: TABLE DATA; Schema: auth; Owner: postgres
--

COPY auth.app_users (user_id, full_name, email, phone, password_hash, is_active, created_at) FROM stdin;
66455818-2653-4201-9a6a-174d925a484b	sar	test@gmail.com	\N	$argon2id$v=19$m=65536,t=3,p=4$kXKuVarVurfWGmPs3RuDEA$YOkrrSlzEYQwZhiKsFhfEY8QCc39j1jQatU1zrWzjrw	t	2026-03-07 05:12:14.603478+05
e12875d7-4de0-4ffd-a5d5-bea0c174d6a0	Sarim	rasheedsarim4@gmail.com	\N	$argon2id$v=19$m=65536,t=3,p=4$ubf2HsO4lxLiXGuN8V7LWQ$8cuVNFHdIgXewjhhE9fJ10BY2Gij2n1VOBey3toPC0w	t	2026-03-17 00:45:22.723516+05
\.


--
-- TOC entry 5312 (class 0 OID 16712)
-- Dependencies: 239
-- Data for Name: user_preferences; Type: TABLE DATA; Schema: auth; Owner: postgres
--

COPY auth.user_preferences (user_id, preferences, updated_at) FROM stdin;
66455818-2653-4201-9a6a-174d925a484b	{}	2026-03-07 05:12:14.603478+05
e12875d7-4de0-4ffd-a5d5-bea0c174d6a0	{}	2026-03-17 00:45:22.723516+05
\.


--
-- TOC entry 5322 (class 0 OID 16939)
-- Dependencies: 249
-- Data for Name: messages; Type: TABLE DATA; Schema: chat; Owner: postgres
--

COPY chat.messages (message_id, session_id, user_id, role, message_text, message_type, tool_name, tool_payload, tokens_used, created_at, metadata) FROM stdin;
\.


--
-- TOC entry 5320 (class 0 OID 16915)
-- Dependencies: 247
-- Data for Name: sessions; Type: TABLE DATA; Schema: chat; Owner: postgres
--

COPY chat.sessions (session_id, user_id, session_title, session_type, language, started_at, last_activity_at, is_active, context_data) FROM stdin;
\.


--
-- TOC entry 5332 (class 0 OID 17162)
-- Dependencies: 259
-- Data for Name: tool_calls; Type: TABLE DATA; Schema: chat; Owner: postgres
--

COPY chat.tool_calls (tool_call_id, session_id, message_id, user_id, tool_name, tool_input, tool_output, status, error_message, execution_time_ms, called_at, metadata) FROM stdin;
\.


--
-- TOC entry 5324 (class 0 OID 16969)
-- Dependencies: 251
-- Data for Name: voice_interactions; Type: TABLE DATA; Schema: chat; Owner: postgres
--

COPY chat.voice_interactions (interaction_id, session_id, user_id, input_audio_path, input_transcript, detected_language, assistant_response_text, output_audio_path, stt_provider, tts_provider, processing_status, created_at, metadata) FROM stdin;
\.


--
-- TOC entry 5307 (class 0 OID 16576)
-- Dependencies: 234
-- Data for Name: cart; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cart (cart_id, status, updated_at, user_id) FROM stdin;
242039df-1f49-4fa1-bf7c-97eb95781a2d	inactive	2026-03-07 05:22:16.573491+05	66455818-2653-4201-9a6a-174d925a484b
029a7fed-7068-40b1-bb42-deb486cc8bea	inactive	2026-03-16 15:25:43.249427+05	66455818-2653-4201-9a6a-174d925a484b
dc3d91ae-99d5-4857-a7f6-6ad41c643bfe	inactive	2026-03-16 15:46:47.564571+05	66455818-2653-4201-9a6a-174d925a484b
129e90c6-b9a6-4628-91fc-db6810483123	inactive	2026-03-16 15:54:24.916129+05	66455818-2653-4201-9a6a-174d925a484b
419152fe-b617-4694-821e-47602febafb1	active	2026-03-16 15:54:25.280115+05	66455818-2653-4201-9a6a-174d925a484b
6ba47b6c-6f79-431d-a701-1beef9a11f9c	inactive	2026-03-17 02:45:24.837777+05	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0
6d31f526-126a-4255-9b54-e8bd68e2a77a	inactive	2026-03-17 02:50:47.323572+05	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0
50e31f55-f808-43cd-847d-1de074a6c781	inactive	2026-03-17 02:51:39.536123+05	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0
daece598-d6a7-40e3-a7b1-3d8d8320e539	inactive	2026-03-17 03:03:57.169781+05	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0
697b48c8-2354-435e-ae57-3fe13197849e	inactive	2026-03-17 03:04:55.35592+05	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0
a16830a7-4a90-4889-bcc4-bf27ca18e566	inactive	2026-03-17 03:39:17.303688+05	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0
79e9903f-f503-4f8f-9ec6-f494ca6943c0	active	2026-03-17 03:39:17.576533+05	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0
\.


--
-- TOC entry 5310 (class 0 OID 16599)
-- Dependencies: 237
-- Data for Name: cart_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cart_items (cart_id, item_id, item_type, item_name, quantity, unit_price) FROM stdin;
\.


--
-- TOC entry 5297 (class 0 OID 16474)
-- Dependencies: 224
-- Data for Name: chef; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.chef (cheff_id, cheff_name, specialty, active_status, max_current_orders) FROM stdin;
1	Ali Khan	BBQ	t	4
2	Shah Ali	BBQ	t	4
3	Imran Qureshi	Desi	t	3
4	Fatima Noor	Desi	t	3
5	abdul mateen	Fast Food	t	3
6	akbar ahmed	Fast Food	t	3
7	esha khurram	Chinese	t	2
8	abid Ali	Chinese	t	3
9	Rashid Khan	Breads	t	6
10	Fazal Haq	Drinks	t	5
\.


--
-- TOC entry 5301 (class 0 OID 16500)
-- Dependencies: 228
-- Data for Name: deal; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.deal (deal_id, deal_name, deal_price, active, serving_size, image_url) FROM stdin;
5	Fast Food Big Party	5535.00	t	6	assets/images/deals/deal_fastfood.jpeg
1	Fast Solo A	720.00	t	1	assets/images/deals/deal_fastfood.jpeg
2	Fast Solo B	877.50	t	1	assets/images/deals/deal_fastfood.jpeg
3	Fast Duo	1620.00	t	2	assets/images/deals/deal_fastfood.jpeg
4	Fast Squad	3532.50	t	4	assets/images/deals/deal_fastfood.jpeg
6	Chinese Solo	1080.00	t	1	assets/images/deals/deal_chinese.jpeg
7	Chinese Duo	1935.00	t	2	assets/images/deals/deal_chinese.jpeg
8	Chinese Squad A	5670.00	t	4	assets/images/deals/deal_chinese.jpeg
9	Chinese Squad B	4950.00	t	4	assets/images/deals/deal_chinese.jpeg
10	Chinese Party Variety	5850.00	t	6	assets/images/deals/deal_chinese.jpeg
11	BBQ Solo	1350.00	t	1	assets/images/deals/deal_bbq.jpeg
12	BBQ Duo	2187.00	t	2	assets/images/deals/deal_bbq.jpeg
13	BBQ Squad	4725.00	t	4	assets/images/deals/deal_bbq.jpeg
14	BBQ Party A	7758.00	t	6	assets/images/deals/deal_bbq.jpeg
15	BBQ Party B	7641.00	t	6	assets/images/deals/deal_bbq.jpeg
16	Desi Solo	855.00	t	1	assets/images/deals/deal_desi.jpeg
17	Desi Duo	990.00	t	2	assets/images/deals/deal_desi.jpeg
18	Desi Squad A	4590.00	t	4	assets/images/deals/deal_desi.jpeg
19	Desi Squad B	4815.00	t	4	assets/images/deals/deal_desi.jpeg
20	Desi Party	7227.00	t	6	assets/images/deals/deal_desi.jpeg
\.


--
-- TOC entry 5302 (class 0 OID 16511)
-- Dependencies: 229
-- Data for Name: deal_item; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.deal_item (deal_id, menu_item_id, quantity) FROM stdin;
1	1	1
1	4	1
1	36	1
2	2	1
2	7	1
2	37	1
3	1	2
3	4	2
3	37	2
4	8	2
4	2	1
4	1	1
4	10	2
4	36	4
5	1	2
5	9	1
5	3	1
5	2	2
5	42	2
5	41	2
5	36	1
5	37	1
5	4	1
5	10	1
5	7	1
5	5	1
6	13	1
6	39	1
7	11	1
7	17	1
7	44	2
8	18	1
8	13	1
8	16	2
8	17	1
8	43	4
9	19	2
9	14	2
9	41	4
10	12	1
10	11	1
10	14	2
10	17	1
10	43	6
11	31	1
11	37	1
11	45	1
12	32	1
12	38	2
12	46	4
13	31	1
13	35	1
13	32	1
13	36	4
13	47	4
14	34	2
14	33	2
14	41	6
14	48	3
14	46	3
15	32	3
15	31	1
15	42	6
15	49	4
15	47	3
16	23	1
16	40	1
16	45	1
17	27	2
17	44	2
17	28	2
18	29	2
18	25	4
18	38	4
19	21	1
19	22	1
19	26	1
19	37	4
20	30	2
20	22	1
20	47	3
20	36	3
20	38	3
20	49	3
\.


--
-- TOC entry 5334 (class 0 OID 17215)
-- Dependencies: 261
-- Data for Name: feedback; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.feedback (feedback_id, user_id, order_id, rating, message, feedback_type, status, created_at) FROM stdin;
1	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0	10	5	ee	GENERAL	NEW	2026-03-17 03:39:33.586874
\.


--
-- TOC entry 5330 (class 0 OID 17122)
-- Dependencies: 257
-- Data for Name: kitchen_task_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.kitchen_task_history (history_id, task_id, order_id, old_status, new_status, old_cheff_id, new_cheff_id, changed_by, notes, changed_at, metadata) FROM stdin;
\.


--
-- TOC entry 5304 (class 0 OID 16546)
-- Dependencies: 231
-- Data for Name: kitchen_tasks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.kitchen_tasks (task_id, order_id, menu_item_id, item_name, qty, station, assigned_chef, estimated_minutes, status, created_at, updated_at) FROM stdin;
1-1	1	1	Cheeseburger	1	FRY	abdul mateen	15	QUEUED	2026-03-07 05:22:16.573491+05	2026-03-07 05:22:16.573491+05
1-2	1	2	Chicken Burger	1	FRY	akbar ahmed	15	QUEUED	2026-03-07 05:22:16.573491+05	2026-03-07 05:22:16.573491+05
1-3	1	8	Club Sandwich	2	FRY	abdul mateen	15	QUEUED	2026-03-07 05:22:16.573491+05	2026-03-07 05:22:16.573491+05
1-4	1	10	Loaded Fries	2	FRY	akbar ahmed	10	QUEUED	2026-03-07 05:22:16.573491+05	2026-03-07 05:22:16.573491+05
1-5	1	36	Cola	4	DRINKS	Fazal Haq	2	QUEUED	2026-03-07 05:22:16.573491+05	2026-03-07 05:22:16.573491+05
2-1	2	1	Cheeseburger	1	FRY	abdul mateen	15	QUEUED	2026-03-16 15:25:43.249427+05	2026-03-16 15:25:43.249427+05
2-2	2	4	Fries	1	FRY	akbar ahmed	10	QUEUED	2026-03-16 15:25:43.249427+05	2026-03-16 15:25:43.249427+05
2-3	2	36	Cola	1	DRINKS	Fazal Haq	2	QUEUED	2026-03-16 15:25:43.249427+05	2026-03-16 15:25:43.249427+05
3-1	3	1	Cheeseburger	1	FRY	abdul mateen	15	QUEUED	2026-03-16 15:46:47.564571+05	2026-03-16 15:46:47.564571+05
3-2	3	4	Fries	1	FRY	akbar ahmed	10	QUEUED	2026-03-16 15:46:47.564571+05	2026-03-16 15:46:47.564571+05
3-3	3	36	Cola	1	DRINKS	Fazal Haq	2	QUEUED	2026-03-16 15:46:47.564571+05	2026-03-16 15:46:47.564571+05
4-1	4	1	Cheeseburger	1	FRY	abdul mateen	15	QUEUED	2026-03-16 15:54:24.916129+05	2026-03-16 15:54:24.916129+05
4-2	4	4	Fries	1	FRY	akbar ahmed	10	QUEUED	2026-03-16 15:54:24.916129+05	2026-03-16 15:54:24.916129+05
4-3	4	36	Cola	1	DRINKS	Fazal Haq	2	QUEUED	2026-03-16 15:54:24.916129+05	2026-03-16 15:54:24.916129+05
5-1	5	1	Cheeseburger	1	FRY	abdul mateen	15	QUEUED	2026-03-17 02:45:24.837777+05	2026-03-17 02:45:24.837777+05
5-2	5	4	Fries	1	FRY	akbar ahmed	10	QUEUED	2026-03-17 02:45:24.837777+05	2026-03-17 02:45:24.837777+05
5-3	5	36	Cola	1	DRINKS	Fazal Haq	2	QUEUED	2026-03-17 02:45:24.837777+05	2026-03-17 02:45:24.837777+05
6-1	6	2	Chicken Burger	1	FRY	abdul mateen	15	QUEUED	2026-03-17 02:50:47.323572+05	2026-03-17 02:50:47.323572+05
6-2	6	7	Onion Rings	1	FRY	akbar ahmed	10	QUEUED	2026-03-17 02:50:47.323572+05	2026-03-17 02:50:47.323572+05
6-3	6	37	Lemonade	1	DRINKS	Fazal Haq	5	QUEUED	2026-03-17 02:50:47.323572+05	2026-03-17 02:50:47.323572+05
7-1	7	3	Veggie Burger	1	FRY	abdul mateen	15	QUEUED	2026-03-17 02:51:39.536123+05	2026-03-17 02:51:39.536123+05
7-2	7	5	Chicken Nuggets	1	FRY	akbar ahmed	10	QUEUED	2026-03-17 02:51:39.536123+05	2026-03-17 02:51:39.536123+05
7-3	7	6	Fish Fillet Sandwich	1	FRY	abdul mateen	15	QUEUED	2026-03-17 02:51:39.536123+05	2026-03-17 02:51:39.536123+05
7-4	7	39	Green Tea	2	DRINKS	Fazal Haq	5	QUEUED	2026-03-17 02:51:39.536123+05	2026-03-17 02:51:39.536123+05
8-1	8	2	Chicken Burger	1	FRY	akbar ahmed	15	QUEUED	2026-03-17 03:03:57.169781+05	2026-03-17 03:03:57.169781+05
8-2	8	7	Onion Rings	1	FRY	abdul mateen	10	QUEUED	2026-03-17 03:03:57.169781+05	2026-03-17 03:03:57.169781+05
8-3	8	37	Lemonade	1	DRINKS	Fazal Haq	5	QUEUED	2026-03-17 03:03:57.169781+05	2026-03-17 03:03:57.169781+05
9-1	9	1	Cheeseburger	1	FRY	akbar ahmed	15	QUEUED	2026-03-17 03:04:55.35592+05	2026-03-17 03:04:55.35592+05
9-2	9	4	Fries	1	FRY	abdul mateen	10	QUEUED	2026-03-17 03:04:55.35592+05	2026-03-17 03:04:55.35592+05
9-3	9	36	Cola	1	DRINKS	Fazal Haq	2	QUEUED	2026-03-17 03:04:55.35592+05	2026-03-17 03:04:55.35592+05
10-1	10	2	Chicken Burger	1	FRY	akbar ahmed	15	QUEUED	2026-03-17 03:39:17.303688+05	2026-03-17 03:39:17.303688+05
10-2	10	7	Onion Rings	1	FRY	abdul mateen	10	QUEUED	2026-03-17 03:39:17.303688+05	2026-03-17 03:39:17.303688+05
10-3	10	37	Lemonade	1	DRINKS	Fazal Haq	5	QUEUED	2026-03-17 03:39:17.303688+05	2026-03-17 03:39:17.303688+05
\.


--
-- TOC entry 5299 (class 0 OID 16486)
-- Dependencies: 226
-- Data for Name: menu_item; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.menu_item (item_id, item_name, item_description, item_category, item_cuisine, item_price, item_cost, tags, availability, serving_size, quantity_description, prep_time_minutes, image_url) FROM stdin;
12	Sweet and Sour Chicken	Crispy chicken in tangy sauce	main	Chinese	1150.00	690.00	{chicken,sweet,tangy,contains_gluten,halal}	t	3	600g	20	assets/images/menu/chinese/manchurian.jpeg
13	Chicken Chow Mein	Stir-fried noodles with chicken and vegetables	main	Chinese	1000.00	600.00	{chicken,noodles,mild,contains_gluten,contains_soy,halal}	t	2	500g	20	assets/images/menu/chinese/chow_mein.jpeg
14	Vegetable Spring Rolls	Crispy rolls with mixed vegetable filling	starter	Chinese	600.00	360.00	{vegetarian,starter,mild,contains_gluten,vegan}	t	2	6 pieces	10	assets/images/menu/chinese/spring_rolls.jpeg
15	Beef with Black Bean Sauce	Sliced beef in savory black bean sauce	main	Chinese	1350.00	810.00	{beef,sauce,mild,contains_soy,halal}	t	3	600g	20	assets/images/menu/chinese/manchurian.jpeg
16	Egg Fried Rice	Rice stir-fried with egg and vegetables	side	Chinese	800.00	480.00	{vegetarian,rice,mild,contains_eggs,contains_soy}	t	2	300g	10	assets/images/menu/chinese/chow_mein.jpeg
17	Hot and Sour Soup	Spicy, tangy soup with tofu and veggies	starter	Chinese	850.00	510.00	{vegetarian,soup,spicy,tangy,vegan,contains_soy}	t	4	1 bowl of 600ml	15	assets/images/menu/chinese/hot_sour_soup.jpeg
18	Szechuan Beef	Spicy beef with Szechuan peppers	main	Chinese	1450.00	870.00	{beef,very_spicy,contains_soy,halal}	t	3	600g	25	assets/images/menu/chinese/kung_pao.jpeg
19	Chicken Manchurian	Fried chicken balls in spicy sauce	main	Chinese	1250.00	750.00	{chicken,spicy,contains_gluten,contains_soy,halal}	t	3	600g	20	assets/images/menu/chinese/manchurian.jpeg
20	Fish Crackers	Crispy fish-flavored snacks	side	Chinese	500.00	300.00	{fish,snack,mild,contains_gluten}	t	2	12-15 pieces	5	assets/images/menu/chinese/spring_rolls.jpeg
30	Chicken Handi	Creamy chicken curry cooked in a clay pot	main	Desi	2400.00	1440.00	{chicken,curry,creamy,mild_spicy,contains_dairy,halal,goes_with_naan}	t	4	1kg	30	assets/images/menu/desi/chicken_karahi.jpeg
1	Cheeseburger	Classic beef patty with cheese, lettuce, tomato, and sauce	main	Fast Food	450.00	270.00	{beef,burger,mild,contains_dairy,contains_gluten,halal}	t	1	1 burger (200g)	15	assets/images/menu/fast_food/burger.jpeg
2	Chicken Burger	Crispy chicken fillet, mayo, lettuce, and tomato	main	Fast Food	375.00	225.00	{chicken,burger,mild,contains_dairy,contains_gluten,halal}	t	1	1 burger (180g)	15	assets/images/menu/fast_food/chicken_burger.jpeg
3	Veggie Burger	Grilled vegetable patty with cheese and greens	main	Fast Food	300.00	180.00	{vegetarian,burger,mild,contains_dairy,contains_gluten}	t	1	1 burger (170g)	15	assets/images/menu/fast_food/burger.jpeg
4	Fries	Golden fried potato sticks	side	Fast Food	200.00	120.00	{vegetarian,fries,non_spicy,vegan,gluten_free,all_year}	t	1	150g	10	assets/images/menu/fast_food/fries.jpeg
5	Chicken Nuggets	Breaded chicken bites with dip	side	Fast Food	450.00	270.00	{chicken,nuggets,mild,contains_gluten,halal}	t	1	8 pieces (120g)	10	assets/images/menu/fast_food/nuggets.jpeg
6	Fish Fillet Sandwich	Fried fish fillet, tartar sauce, lettuce	main	Fast Food	650.00	390.00	{fish,sandwich,mild,contains_gluten,contains_dairy}	t	1	1 sandwich (250g)	15	assets/images/menu/fast_food/burger.jpeg
7	Onion Rings	Crispy battered onion rings	side	Fast Food	350.00	210.00	{vegetarian,onion,mild,contains_gluten}	t	1	8 rings (120g)	10	assets/images/menu/fast_food/fries.jpeg
8	Club Sandwich	Triple-layered sandwich with chicken, egg, and veggies	main	Fast Food	700.00	420.00	{chicken,sandwich,mild,contains_eggs,contains_gluten,contains_dairy}	t	1	4 pieces (300g)	15	assets/images/menu/fast_food/burger.jpeg
9	Zinger Burger	Spicy fried chicken fillet, lettuce, and mayo	main	Fast Food	550.00	330.00	{chicken,spicy,burger,contains_dairy,contains_gluten,halal}	t	1	1 burger (200g)	15	assets/images/menu/fast_food/chicken_burger.jpeg
10	Loaded Fries	Fries topped with cheese, jalapenos, chicken, and sauce	side	Fast Food	550.00	330.00	{vegetarian,fries,chicken,cheese,mild_spicy,contains_dairy}	t	1	200g	10	assets/images/menu/fast_food/loaded_fries.jpeg
31	Chicken Tikka	Marinated chicken pieces grilled on skewers	main	BBQ	1200.00	720.00	{chicken,grilled,bbq,spicy,contains_dairy,halal,gluten_free}	t	2	1 leg and 1 chest piece	20	https://yourcdn.com/menu/bbq.jpg
32	Beef Boti	Cubes of beef marinated and grilled	main	BBQ	1450.00	870.00	{beef,grilled,bbq,spicy,contains_dairy,halal,gluten_free}	t	4	12 pieces	25	https://yourcdn.com/menu/bbq.jpg
33	Malai Boti	Creamy, tender chicken cubes grilled	main	BBQ	1400.00	840.00	{chicken,creamy,grilled,bbq,mild,contains_dairy,halal,gluten_free}	t	4	12 pieces	20	https://yourcdn.com/menu/bbq.jpg
34	Reshmi Kebab	Soft, silky chicken kebabs	main	BBQ	1350.00	810.00	{chicken,kebab,bbq,mild,contains_dairy,halal,gluten_free}	t	4	8 pieces	25	https://yourcdn.com/menu/bbq.jpg
35	Grilled Fish	Spiced fish fillet grilled over charcoal	main	BBQ	1600.00	960.00	{fish,grilled,bbq,spicy,gluten_free,seasonal_summer}	t	4	800g	20	https://yourcdn.com/menu/bbq.jpg
11	Kung Pao Chicken	Stir-fried chicken with peanuts and chili	main	Chinese	1200.00	720.00	{chicken,spicy,contains_nuts,contains_soy,halal}	t	3	600g	20	assets/images/menu/chinese/kung_pao.jpeg
21	Chicken Karahi	Spicy chicken curry with tomatoes and green chilies	main	Desi	2250.00	1350.00	{chicken,spicy,curry,contains_dairy,halal,goes_with_naan}	t	4	1kg	30	assets/images/menu/desi/chicken_karahi.jpeg
22	Beef Biryani	Aromatic rice with beef and spices	main	Desi	1250.00	750.00	{beef,rice,mild_spicy,contains_dairy,halal}	t	3	1 plate (500g)	15	assets/images/menu/desi/biryani.jpeg
23	Daal Chawal	Lentil curry served with rice	main	Desi	650.00	390.00	{vegetarian,lentil,rice,mild,vegan,gluten_free}	t	2	1 plate (350g)	10	assets/images/menu/desi/daal_chawal.jpeg
24	Nihari	Slow-cooked beef stew	main	Desi	1350.00	810.00	{beef,stew,mild_spicy,halal,goes_with_naan}	t	4	500g	25	assets/images/menu/desi/nihari.jpeg
25	Aloo Paratha	Flatbread stuffed with spiced potatoes	bread	Desi	250.00	150.00	{vegetarian,bread,mild,contains_gluten,contains_dairy}	t	1	1 piece	10	assets/images/menu/desi/paratha.jpeg
26	Palak Paneer	Spinach curry with cottage cheese	main	Desi	850.00	510.00	{vegetarian,cheese,curry,mild,contains_dairy,goes_with_naan}	t	3	1 plate (600g)	20	assets/images/menu/desi/chicken_karahi.jpeg
27	Chana Chaat	Spicy chickpea salad	starter	Desi	150.00	90.00	{vegetarian,chickpea,salad,tangy,spicy,vegan,gluten_free}	t	1	200g	5	assets/images/menu/desi/chana_chaat.jpeg
28	Samosa Platter	Fried pastry with potato and pea filling	starter	Desi	250.00	150.00	{vegetarian,starter,pastry,mild_spicy,contains_gluten,vegan}	t	1	2 samosa pieces	5	assets/images/menu/desi/samosa.jpeg
29	Seekh Kabab	Minced meat skewers grilled to perfection	main	Desi	1350.00	810.00	{meat,kebab,spicy,halal,gluten_free}	t	4	8 kababs	25	assets/images/menu/desi/nihari.jpeg
45	Roti	Traditional whole wheat flatbread, soft and fresh	bread	Desi	50.00	30.00	{bread,wheat,mild,vegan,all_year}	t	1	1 piece	1	assets/images/menu/bread/roti.jpeg
46	Naan	Soft, leavened white flour bread, baked in a tandoor	bread	Desi	70.00	42.00	{bread,white_flour,mild,contains_dairy,vegetarian,all_year}	t	1	1 piece	1	assets/images/menu/bread/naan.jpeg
47	Garlic Naan	Naan topped with garlic and herbs	bread	Desi	100.00	60.00	{bread,garlic,mild,contains_dairy,vegetarian,all_year}	t	1	1 piece	3	assets/images/menu/bread/garlic_naan.jpeg
48	Paratha	Flaky, layered flatbread, pan-fried with ghee	bread	Desi	70.00	42.00	{bread,ghee,mild,contains_dairy,vegetarian,all_year}	t	1	1 piece	3	assets/images/menu/bread/paratha.jpeg
49	Chapatti	Thin, soft whole wheat flatbread	bread	Desi	60.00	36.00	{bread,wheat,mild,vegan,all_year}	t	1	1 piece	1	assets/images/menu/bread/roti.jpeg
36	Cola	Chilled carbonated soft drink	drink	Drinks	150.00	90.00	{cold,soft_drink,non_spicy,vegan,gluten_free,all_year}	t	1	330 ml	2	assets/images/menu/drinks/cola.jpeg
37	Lemonade	Freshly squeezed lemon juice with sugar	drink	Drinks	250.00	150.00	{cold,lemon,tangy,vegan,gluten_free,seasonal_summer}	t	1	400 ml	5	assets/images/menu/drinks/lemonade.jpeg
38	Mint Margarita	Refreshing mint and lemon mocktail	drink	Drinks	350.00	210.00	{cold,mint,mocktail,refreshing,vegan,gluten_free,seasonal_summer}	t	1	350 ml	5	assets/images/menu/drinks/mint_margarita.jpeg
39	Green Tea	Hot brewed green tea	drink	Drinks	200.00	120.00	{hot,tea,mild,vegan,gluten_free,all_year}	t	1	250 ml	5	assets/images/menu/drinks/chai.jpeg
40	Chai	Milk tea, a South Asian favorite	drink	Drinks	250.00	150.00	{hot,tea,milk,sweet,contains_dairy,all_year}	t	1	250 ml	5	assets/images/menu/drinks/chai.jpeg
41	Iced Coffee	Chilled coffee with milk and ice	drink	Drinks	450.00	270.00	{cold,coffee,milk,contains_dairy,all_year}	t	1	350 ml	5	assets/images/menu/drinks/iced_coffee.jpeg
42	Strawberry Shake	Creamy milkshake with fresh strawberries	drink	Drinks	400.00	240.00	{cold,shake,strawberry,sweet,contains_dairy,seasonal_summer}	t	1	350 ml	5	assets/images/menu/drinks/lemonade.jpeg
43	Orange Juice	Freshly squeezed orange juice	drink	Drinks	350.00	210.00	{cold,juice,orange,sweet,vegan,gluten_free,seasonal_winter}	t	1	300 ml	5	assets/images/menu/drinks/lemonade.jpeg
44	Water Bottle	Chilled mineral water	drink	Drinks	150.00	90.00	{cold,water,non_spicy,vegan,gluten_free,all_year}	t	1	500 ml	2	assets/images/menu/drinks/cola.jpeg
\.


--
-- TOC entry 5303 (class 0 OID 16529)
-- Dependencies: 230
-- Data for Name: menu_item_chefs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.menu_item_chefs (menu_item_id, chef_id) FROM stdin;
31	1
32	1
33	1
34	1
35	1
31	2
32	2
33	2
34	2
35	2
21	3
22	3
23	3
24	3
26	3
27	3
28	3
29	3
30	3
21	4
22	4
23	4
24	4
26	4
27	4
28	4
29	4
30	4
1	5
2	5
3	5
4	5
5	5
6	5
7	5
8	5
9	5
10	5
1	6
2	6
3	6
4	6
5	6
6	6
7	6
8	6
9	6
10	6
11	7
12	7
13	7
14	7
15	7
16	7
17	7
18	7
19	7
20	7
11	8
12	8
13	8
14	8
15	8
16	8
17	8
18	8
19	8
20	8
25	9
45	9
46	9
47	9
48	9
49	9
36	10
37	10
38	10
39	10
40	10
41	10
42	10
43	10
44	10
\.


--
-- TOC entry 5306 (class 0 OID 16562)
-- Dependencies: 233
-- Data for Name: offers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.offers (offer_id, title, description, offer_code, validity, category) FROM stdin;
1	Weekend Special Combo	Buy 1 large pizza, get 1 small free!	WEEKEND50	2025-12-15	Fast Food
2	Burger Bonanza	Flat 25% off on all burger meals.	BURGER25	2025-12-17	Fast Food
3	Family Feast Offer	Free dessert on orders above Rs 5000.	FAMILYFEAST	2025-12-20	Desi
\.


--
-- TOC entry 5328 (class 0 OID 17018)
-- Dependencies: 255
-- Data for Name: order_events; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.order_events (event_id, order_id, event_type, event_source, event_data, created_at) FROM stdin;
\.


--
-- TOC entry 5314 (class 0 OID 16768)
-- Dependencies: 241
-- Data for Name: order_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.order_items (id, order_id, item_type, item_id, name_snapshot, unit_price_snapshot, quantity, line_total) FROM stdin;
1	1	deal	4	Fast Squad	3532.50	1	3532.50
2	2	deal	1	Fast Solo A	720.00	1	720.00
3	3	deal	1	Fast Solo A	720.00	1	720.00
4	4	deal	1	Fast Solo A	720.00	1	720.00
5	5	deal	1	Fast Solo A	720.00	1	720.00
6	6	deal	2	Fast Solo B	877.50	1	877.50
7	7	menu_item	3	Veggie Burger	300.00	1	300.00
8	7	menu_item	5	Chicken Nuggets	450.00	1	450.00
9	7	menu_item	6	Fish Fillet Sandwich	650.00	1	650.00
10	7	menu_item	39	Green Tea	200.00	2	400.00
11	8	deal	2	Fast Solo B	877.50	1	877.50
12	9	deal	1	Fast Solo A	720.00	1	720.00
13	10	deal	2	Fast Solo B	877.50	1	877.50
\.


--
-- TOC entry 5326 (class 0 OID 16997)
-- Dependencies: 253
-- Data for Name: order_status_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.order_status_history (id, order_id, old_status, new_status, changed_by, notes, changed_at) FROM stdin;
\.


--
-- TOC entry 5309 (class 0 OID 16581)
-- Dependencies: 236
-- Data for Name: orders; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.orders (order_id, cart_id, total_price, estimated_prep_time_minutes, order_data, created_at, status, updated_at, delivery_address, subtotal, tax, delivery_fee, payment_method) FROM stdin;
1	242039df-1f49-4fa1-bf7c-97eb95781a2d	3859.12	15	{"tax": 176.62, "items": [{"item_id": 4, "quantity": 1, "item_name": "Fast Squad", "item_type": "deal", "line_total": 3532.5, "unit_price": 3532.5}], "subtotal": 3532.5, "total_price": 3859.12, "delivery_fee": 150.0}	2026-03-07 05:22:16.573491+05	confirmed	2026-03-07 05:22:16.573491+05	123 Main	3532.50	176.62	150.00	\N
2	029a7fed-7068-40b1-bb42-deb486cc8bea	906.00	15	{"tax": 36.0, "items": [{"item_id": 1, "quantity": 1, "item_name": "Fast Solo A", "item_type": "deal", "line_total": 720.0, "unit_price": 720.0}], "subtotal": 720.0, "total_price": 906.0, "delivery_fee": 150.0}	2026-03-16 15:25:43.249427+05	confirmed	2026-03-16 15:25:43.249427+05	123 Main St, City, State 12345	720.00	36.00	150.00	\N
3	dc3d91ae-99d5-4857-a7f6-6ad41c643bfe	906.00	15	{"tax": 36.0, "items": [{"item_id": 1, "quantity": 1, "item_name": "Fast Solo A", "item_type": "deal", "line_total": 720.0, "unit_price": 720.0}], "subtotal": 720.0, "total_price": 906.0, "delivery_fee": 150.0}	2026-03-16 15:46:47.564571+05	confirmed	2026-03-16 15:46:47.564571+05	123 Main St, City, State 12345	720.00	36.00	150.00	\N
4	129e90c6-b9a6-4628-91fc-db6810483123	906.00	15	{"tax": 36.0, "items": [{"item_id": 1, "quantity": 1, "item_name": "Fast Solo A", "item_type": "deal", "line_total": 720.0, "unit_price": 720.0}], "subtotal": 720.0, "total_price": 906.0, "delivery_fee": 150.0}	2026-03-16 15:54:24.916129+05	confirmed	2026-03-16 15:54:24.916129+05	123 Main St, City, State 12345	720.00	36.00	150.00	\N
5	6ba47b6c-6f79-431d-a701-1beef9a11f9c	906.00	15	{"tax": 36.0, "items": [{"item_id": 1, "quantity": 1, "item_name": "Fast Solo A", "item_type": "deal", "line_total": 720.0, "unit_price": 720.0}], "subtotal": 720.0, "total_price": 906.0, "delivery_fee": 150.0}	2026-03-17 02:45:24.837777+05	confirmed	2026-03-17 02:45:24.837777+05	123 Main St, City, State 12345	720.00	36.00	150.00	\N
6	6d31f526-126a-4255-9b54-e8bd68e2a77a	1071.38	15	{"tax": 43.88, "items": [{"item_id": 2, "quantity": 1, "item_name": "Fast Solo B", "item_type": "deal", "line_total": 877.5, "unit_price": 877.5}], "subtotal": 877.5, "total_price": 1071.38, "delivery_fee": 150.0}	2026-03-17 02:50:47.323572+05	confirmed	2026-03-17 02:50:47.323572+05	123 Main St, City, State 12345	877.50	43.88	150.00	\N
7	50e31f55-f808-43cd-847d-1de074a6c781	2040.00	15	{"tax": 90.0, "items": [{"item_id": 3, "quantity": 1, "item_name": "Veggie Burger", "item_type": "menu_item", "line_total": 300.0, "unit_price": 300.0}, {"item_id": 5, "quantity": 1, "item_name": "Chicken Nuggets", "item_type": "menu_item", "line_total": 450.0, "unit_price": 450.0}, {"item_id": 6, "quantity": 1, "item_name": "Fish Fillet Sandwich", "item_type": "menu_item", "line_total": 650.0, "unit_price": 650.0}, {"item_id": 39, "quantity": 2, "item_name": "Green Tea", "item_type": "menu_item", "line_total": 400.0, "unit_price": 200.0}], "subtotal": 1800.0, "total_price": 2040.0, "delivery_fee": 150.0}	2026-03-17 02:51:39.536123+05	confirmed	2026-03-17 02:51:39.536123+05	123 Main St, City, State 12345	1800.00	90.00	150.00	\N
8	daece598-d6a7-40e3-a7b1-3d8d8320e539	1071.38	15	{"tax": 43.88, "items": [{"item_id": 2, "quantity": 1, "item_name": "Fast Solo B", "item_type": "deal", "line_total": 877.5, "unit_price": 877.5}], "subtotal": 877.5, "total_price": 1071.38, "delivery_fee": 150.0}	2026-03-17 03:03:57.169781+05	confirmed	2026-03-17 03:03:57.169781+05	123 Main St, City, State 12345	877.50	43.88	150.00	COD
9	697b48c8-2354-435e-ae57-3fe13197849e	906.00	15	{"tax": 36.0, "items": [{"item_id": 1, "quantity": 1, "item_name": "Fast Solo A", "item_type": "deal", "line_total": 720.0, "unit_price": 720.0}], "subtotal": 720.0, "total_price": 906.0, "delivery_fee": 150.0}	2026-03-17 03:04:55.35592+05	confirmed	2026-03-17 03:04:55.35592+05	123 Main St, City, State 12345	720.00	36.00	150.00	CARD
10	a16830a7-4a90-4889-bcc4-bf27ca18e566	1071.38	15	{"tax": 43.88, "items": [{"item_id": 2, "quantity": 1, "item_name": "Fast Solo B", "item_type": "deal", "line_total": 877.5, "unit_price": 877.5}], "subtotal": 877.5, "total_price": 1071.38, "delivery_fee": 150.0}	2026-03-17 03:39:17.303688+05	confirmed	2026-03-17 03:39:17.303688+05	123 Main St, City, State 12345	877.50	43.88	150.00	COD
\.


--
-- TOC entry 5318 (class 0 OID 16874)
-- Dependencies: 245
-- Data for Name: payments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.payments (id, transaction_id, order_id, user_id, card_id, amount, card_last4, card_type, cardholder_name, status, created_at, payment_method) FROM stdin;
1	TXN-1001	1	66455818-2653-4201-9a6a-174d925a484b	1	2500.00	4242	visa	Test User	PENDING	2026-03-16 00:43:28.999918	CARD
2	TXN-4FB080609A4B	\N	66455818-2653-4201-9a6a-174d925a484b	2	906.0	4555	Card	Sarim Rasheed	SUCCESS	2026-03-16 04:49:47.387432	CARD
3	TXN-4AA1CDBB395B	\N	66455818-2653-4201-9a6a-174d925a484b	2	906.0	4555	Card	Sarim Rasheed	SUCCESS	2026-03-16 04:49:52.708716	CARD
4	TXN-92CAEEEB8480	\N	66455818-2653-4201-9a6a-174d925a484b	1	906.0	4242	visa	Test User	SUCCESS	2026-03-16 04:50:00.641451	CARD
5	TXN-409C656889ED	\N	66455818-2653-4201-9a6a-174d925a484b	1	906.0	4242	visa	Test User	SUCCESS	2026-03-16 04:54:14.353379	CARD
6	TXN-A2824161AA54	2	66455818-2653-4201-9a6a-174d925a484b	2	906.0	4555	Card	Sarim Rasheed	SUCCESS	2026-03-16 15:25:42.994306	CARD
7	TXN-47718DDDFCCD	3	66455818-2653-4201-9a6a-174d925a484b	1	906.0	4242	visa	Test User	SUCCESS	2026-03-16 15:46:47.248296	CARD
8	TXN-1B1946A9B7E4	4	66455818-2653-4201-9a6a-174d925a484b	1	906.0	4242	visa	Test User	SUCCESS	2026-03-16 15:54:24.669477	CARD
9	TXN-C418E3CA218C	9	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0	4	906.0	4422	Visa	aarfiiii	SUCCESS	2026-03-17 03:04:55.124446	CARD
\.


--
-- TOC entry 5316 (class 0 OID 16859)
-- Dependencies: 243
-- Data for Name: saved_cards; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.saved_cards (card_id, user_id, card_type, last4, cardholder_name, expiry, is_default, created_at) FROM stdin;
1	66455818-2653-4201-9a6a-174d925a484b	visa	4242	Test User	12/28	f	2026-03-16 00:40:59.338988
2	66455818-2653-4201-9a6a-174d925a484b	Card	4555	Sarim Rasheed	02/30	f	2026-03-16 04:49:41.850688
4	e12875d7-4de0-4ffd-a5d5-bea0c174d6a0	Visa	4422	aarfiiii	01/33	t	2026-03-17 03:04:49.702323
\.


--
-- TOC entry 5357 (class 0 OID 0)
-- Dependencies: 248
-- Name: messages_message_id_seq; Type: SEQUENCE SET; Schema: chat; Owner: postgres
--

SELECT pg_catalog.setval('chat.messages_message_id_seq', 1, false);


--
-- TOC entry 5358 (class 0 OID 0)
-- Dependencies: 246
-- Name: sessions_session_id_seq; Type: SEQUENCE SET; Schema: chat; Owner: postgres
--

SELECT pg_catalog.setval('chat.sessions_session_id_seq', 1, false);


--
-- TOC entry 5359 (class 0 OID 0)
-- Dependencies: 258
-- Name: tool_calls_tool_call_id_seq; Type: SEQUENCE SET; Schema: chat; Owner: postgres
--

SELECT pg_catalog.setval('chat.tool_calls_tool_call_id_seq', 1, false);


--
-- TOC entry 5360 (class 0 OID 0)
-- Dependencies: 250
-- Name: voice_interactions_interaction_id_seq; Type: SEQUENCE SET; Schema: chat; Owner: postgres
--

SELECT pg_catalog.setval('chat.voice_interactions_interaction_id_seq', 1, false);


--
-- TOC entry 5361 (class 0 OID 0)
-- Dependencies: 223
-- Name: chef_cheff_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.chef_cheff_id_seq', 10, true);


--
-- TOC entry 5362 (class 0 OID 0)
-- Dependencies: 227
-- Name: deal_deal_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.deal_deal_id_seq', 20, true);


--
-- TOC entry 5363 (class 0 OID 0)
-- Dependencies: 260
-- Name: feedback_feedback_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.feedback_feedback_id_seq', 1, true);


--
-- TOC entry 5364 (class 0 OID 0)
-- Dependencies: 256
-- Name: kitchen_task_history_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.kitchen_task_history_history_id_seq', 1, false);


--
-- TOC entry 5365 (class 0 OID 0)
-- Dependencies: 225
-- Name: menu_item_item_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.menu_item_item_id_seq', 49, true);


--
-- TOC entry 5366 (class 0 OID 0)
-- Dependencies: 232
-- Name: offers_offer_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.offers_offer_id_seq', 3, true);


--
-- TOC entry 5367 (class 0 OID 0)
-- Dependencies: 254
-- Name: order_events_event_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.order_events_event_id_seq', 1, false);


--
-- TOC entry 5368 (class 0 OID 0)
-- Dependencies: 240
-- Name: order_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.order_items_id_seq', 13, true);


--
-- TOC entry 5369 (class 0 OID 0)
-- Dependencies: 252
-- Name: order_status_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.order_status_history_id_seq', 1, false);


--
-- TOC entry 5370 (class 0 OID 0)
-- Dependencies: 235
-- Name: orders_order_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.orders_order_id_seq', 10, true);


--
-- TOC entry 5371 (class 0 OID 0)
-- Dependencies: 244
-- Name: payments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.payments_id_seq', 9, true);


--
-- TOC entry 5372 (class 0 OID 0)
-- Dependencies: 242
-- Name: saved_cards_card_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.saved_cards_card_id_seq', 4, true);


--
-- TOC entry 5060 (class 2606 OID 16709)
-- Name: app_users app_users_email_key; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.app_users
    ADD CONSTRAINT app_users_email_key UNIQUE (email);


--
-- TOC entry 5062 (class 2606 OID 16711)
-- Name: app_users app_users_phone_key; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.app_users
    ADD CONSTRAINT app_users_phone_key UNIQUE (phone);


--
-- TOC entry 5064 (class 2606 OID 16707)
-- Name: app_users app_users_pkey; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.app_users
    ADD CONSTRAINT app_users_pkey PRIMARY KEY (user_id);


--
-- TOC entry 5066 (class 2606 OID 16723)
-- Name: user_preferences user_preferences_pkey; Type: CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.user_preferences
    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id);


--
-- TOC entry 5085 (class 2606 OID 16953)
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (message_id);


--
-- TOC entry 5080 (class 2606 OID 16930)
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (session_id);


--
-- TOC entry 5112 (class 2606 OID 17177)
-- Name: tool_calls tool_calls_pkey; Type: CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.tool_calls
    ADD CONSTRAINT tool_calls_pkey PRIMARY KEY (tool_call_id);


--
-- TOC entry 5090 (class 2606 OID 16982)
-- Name: voice_interactions voice_interactions_pkey; Type: CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.voice_interactions
    ADD CONSTRAINT voice_interactions_pkey PRIMARY KEY (interaction_id);


--
-- TOC entry 5058 (class 2606 OID 16608)
-- Name: cart_items cart_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_pkey PRIMARY KEY (cart_id, item_id, item_type);


--
-- TOC entry 5051 (class 2606 OID 16598)
-- Name: cart cart_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cart
    ADD CONSTRAINT cart_pkey PRIMARY KEY (cart_id);


--
-- TOC entry 5037 (class 2606 OID 16484)
-- Name: chef chef_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chef
    ADD CONSTRAINT chef_pkey PRIMARY KEY (cheff_id);


--
-- TOC entry 5043 (class 2606 OID 16518)
-- Name: deal_item deal_item_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.deal_item
    ADD CONSTRAINT deal_item_pkey PRIMARY KEY (deal_id, menu_item_id);


--
-- TOC entry 5041 (class 2606 OID 16510)
-- Name: deal deal_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.deal
    ADD CONSTRAINT deal_pkey PRIMARY KEY (deal_id);


--
-- TOC entry 5114 (class 2606 OID 17232)
-- Name: feedback feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_pkey PRIMARY KEY (feedback_id);


--
-- TOC entry 5105 (class 2606 OID 17136)
-- Name: kitchen_task_history kitchen_task_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kitchen_task_history
    ADD CONSTRAINT kitchen_task_history_pkey PRIMARY KEY (history_id);


--
-- TOC entry 5047 (class 2606 OID 16557)
-- Name: kitchen_tasks kitchen_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kitchen_tasks
    ADD CONSTRAINT kitchen_tasks_pkey PRIMARY KEY (task_id);


--
-- TOC entry 5045 (class 2606 OID 16535)
-- Name: menu_item_chefs menu_item_chefs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.menu_item_chefs
    ADD CONSTRAINT menu_item_chefs_pkey PRIMARY KEY (menu_item_id, chef_id);


--
-- TOC entry 5039 (class 2606 OID 16498)
-- Name: menu_item menu_item_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.menu_item
    ADD CONSTRAINT menu_item_pkey PRIMARY KEY (item_id);


--
-- TOC entry 5049 (class 2606 OID 16575)
-- Name: offers offers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.offers
    ADD CONSTRAINT offers_pkey PRIMARY KEY (offer_id);


--
-- TOC entry 5099 (class 2606 OID 17031)
-- Name: order_events order_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_events
    ADD CONSTRAINT order_events_pkey PRIMARY KEY (event_id);


--
-- TOC entry 5069 (class 2606 OID 16784)
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);


--
-- TOC entry 5094 (class 2606 OID 17009)
-- Name: order_status_history order_status_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT order_status_history_pkey PRIMARY KEY (id);


--
-- TOC entry 5054 (class 2606 OID 16806)
-- Name: orders orders_cart_unique; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_cart_unique UNIQUE (cart_id);


--
-- TOC entry 5056 (class 2606 OID 16597)
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (order_id);


--
-- TOC entry 5076 (class 2606 OID 16890)
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- TOC entry 5072 (class 2606 OID 16888)
-- Name: saved_cards saved_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.saved_cards
    ADD CONSTRAINT saved_cards_pkey PRIMARY KEY (card_id);


--
-- TOC entry 5081 (class 1259 OID 16966)
-- Name: idx_chat_messages_created_at; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_chat_messages_created_at ON chat.messages USING btree (created_at);


--
-- TOC entry 5082 (class 1259 OID 16967)
-- Name: idx_chat_messages_role; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_chat_messages_role ON chat.messages USING btree (role);


--
-- TOC entry 5083 (class 1259 OID 16965)
-- Name: idx_chat_messages_session_id; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_chat_messages_session_id ON chat.messages USING btree (session_id);


--
-- TOC entry 5077 (class 1259 OID 16937)
-- Name: idx_chat_sessions_last_activity; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_chat_sessions_last_activity ON chat.sessions USING btree (last_activity_at);


--
-- TOC entry 5078 (class 1259 OID 16936)
-- Name: idx_chat_sessions_user_id; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_chat_sessions_user_id ON chat.sessions USING btree (user_id);


--
-- TOC entry 5106 (class 1259 OID 17198)
-- Name: idx_tool_calls_called_at; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_tool_calls_called_at ON chat.tool_calls USING btree (called_at);


--
-- TOC entry 5107 (class 1259 OID 17195)
-- Name: idx_tool_calls_message_id; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_tool_calls_message_id ON chat.tool_calls USING btree (message_id);


--
-- TOC entry 5108 (class 1259 OID 17194)
-- Name: idx_tool_calls_session_id; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_tool_calls_session_id ON chat.tool_calls USING btree (session_id);


--
-- TOC entry 5109 (class 1259 OID 17197)
-- Name: idx_tool_calls_tool_name; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_tool_calls_tool_name ON chat.tool_calls USING btree (tool_name);


--
-- TOC entry 5110 (class 1259 OID 17196)
-- Name: idx_tool_calls_user_id; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_tool_calls_user_id ON chat.tool_calls USING btree (user_id);


--
-- TOC entry 5086 (class 1259 OID 16995)
-- Name: idx_voice_interactions_created_at; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_voice_interactions_created_at ON chat.voice_interactions USING btree (created_at);


--
-- TOC entry 5087 (class 1259 OID 16993)
-- Name: idx_voice_interactions_session_id; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_voice_interactions_session_id ON chat.voice_interactions USING btree (session_id);


--
-- TOC entry 5088 (class 1259 OID 16994)
-- Name: idx_voice_interactions_user_id; Type: INDEX; Schema: chat; Owner: postgres
--

CREATE INDEX idx_voice_interactions_user_id ON chat.voice_interactions USING btree (user_id);


--
-- TOC entry 5115 (class 1259 OID 17245)
-- Name: idx_feedback_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_feedback_created_at ON public.feedback USING btree (created_at);


--
-- TOC entry 5116 (class 1259 OID 17244)
-- Name: idx_feedback_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_feedback_order_id ON public.feedback USING btree (order_id);


--
-- TOC entry 5117 (class 1259 OID 17243)
-- Name: idx_feedback_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_feedback_user_id ON public.feedback USING btree (user_id);


--
-- TOC entry 5100 (class 1259 OID 17159)
-- Name: idx_kitchen_task_history_changed_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_kitchen_task_history_changed_at ON public.kitchen_task_history USING btree (changed_at);


--
-- TOC entry 5101 (class 1259 OID 17160)
-- Name: idx_kitchen_task_history_new_cheff_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_kitchen_task_history_new_cheff_id ON public.kitchen_task_history USING btree (new_cheff_id);


--
-- TOC entry 5102 (class 1259 OID 17158)
-- Name: idx_kitchen_task_history_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_kitchen_task_history_order_id ON public.kitchen_task_history USING btree (order_id);


--
-- TOC entry 5103 (class 1259 OID 17157)
-- Name: idx_kitchen_task_history_task_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_kitchen_task_history_task_id ON public.kitchen_task_history USING btree (task_id);


--
-- TOC entry 5095 (class 1259 OID 17039)
-- Name: idx_order_events_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_events_created_at ON public.order_events USING btree (created_at);


--
-- TOC entry 5096 (class 1259 OID 17038)
-- Name: idx_order_events_event_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_events_event_type ON public.order_events USING btree (event_type);


--
-- TOC entry 5097 (class 1259 OID 17037)
-- Name: idx_order_events_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_events_order_id ON public.order_events USING btree (order_id);


--
-- TOC entry 5067 (class 1259 OID 16790)
-- Name: idx_order_items_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_items_order_id ON public.order_items USING btree (order_id);


--
-- TOC entry 5091 (class 1259 OID 17016)
-- Name: idx_order_status_history_changed_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_status_history_changed_at ON public.order_status_history USING btree (changed_at);


--
-- TOC entry 5092 (class 1259 OID 17015)
-- Name: idx_order_status_history_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_status_history_order_id ON public.order_status_history USING btree (order_id);


--
-- TOC entry 5073 (class 1259 OID 16913)
-- Name: idx_payments_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_payments_order_id ON public.payments USING btree (order_id);


--
-- TOC entry 5074 (class 1259 OID 16912)
-- Name: idx_payments_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_payments_user_id ON public.payments USING btree (user_id);


--
-- TOC entry 5070 (class 1259 OID 16911)
-- Name: idx_saved_cards_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_saved_cards_user_id ON public.saved_cards USING btree (user_id);


--
-- TOC entry 5052 (class 1259 OID 16796)
-- Name: unique_active_cart_per_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX unique_active_cart_per_user ON public.cart USING btree (user_id) WHERE (status = 'active'::text);


--
-- TOC entry 5148 (class 2620 OID 16730)
-- Name: user_preferences trg_user_preferences_updated; Type: TRIGGER; Schema: auth; Owner: postgres
--

CREATE TRIGGER trg_user_preferences_updated BEFORE UPDATE ON auth.user_preferences FOR EACH ROW EXECUTE FUNCTION auth.set_updated_at();


--
-- TOC entry 5147 (class 2620 OID 16802)
-- Name: orders trg_orders_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_orders_updated BEFORE UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- TOC entry 5125 (class 2606 OID 16724)
-- Name: user_preferences user_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: postgres
--

ALTER TABLE ONLY auth.user_preferences
    ADD CONSTRAINT user_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE CASCADE;


--
-- TOC entry 5132 (class 2606 OID 16954)
-- Name: messages messages_session_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.messages
    ADD CONSTRAINT messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES chat.sessions(session_id) ON DELETE CASCADE;


--
-- TOC entry 5133 (class 2606 OID 16959)
-- Name: messages messages_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.messages
    ADD CONSTRAINT messages_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE SET NULL;


--
-- TOC entry 5131 (class 2606 OID 16931)
-- Name: sessions sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.sessions
    ADD CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE CASCADE;


--
-- TOC entry 5142 (class 2606 OID 17183)
-- Name: tool_calls tool_calls_message_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.tool_calls
    ADD CONSTRAINT tool_calls_message_id_fkey FOREIGN KEY (message_id) REFERENCES chat.messages(message_id) ON DELETE SET NULL;


--
-- TOC entry 5143 (class 2606 OID 17178)
-- Name: tool_calls tool_calls_session_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.tool_calls
    ADD CONSTRAINT tool_calls_session_id_fkey FOREIGN KEY (session_id) REFERENCES chat.sessions(session_id) ON DELETE CASCADE;


--
-- TOC entry 5144 (class 2606 OID 17188)
-- Name: tool_calls tool_calls_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.tool_calls
    ADD CONSTRAINT tool_calls_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE SET NULL;


--
-- TOC entry 5134 (class 2606 OID 16983)
-- Name: voice_interactions voice_interactions_session_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.voice_interactions
    ADD CONSTRAINT voice_interactions_session_id_fkey FOREIGN KEY (session_id) REFERENCES chat.sessions(session_id) ON DELETE CASCADE;


--
-- TOC entry 5135 (class 2606 OID 16988)
-- Name: voice_interactions voice_interactions_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: postgres
--

ALTER TABLE ONLY chat.voice_interactions
    ADD CONSTRAINT voice_interactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE CASCADE;


--
-- TOC entry 5124 (class 2606 OID 16609)
-- Name: cart_items cart_items_cart_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_cart_id_fkey FOREIGN KEY (cart_id) REFERENCES public.cart(cart_id) ON DELETE CASCADE;


--
-- TOC entry 5122 (class 2606 OID 16791)
-- Name: cart cart_user_fk; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cart
    ADD CONSTRAINT cart_user_fk FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE CASCADE;


--
-- TOC entry 5118 (class 2606 OID 16519)
-- Name: deal_item deal_item_deal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.deal_item
    ADD CONSTRAINT deal_item_deal_id_fkey FOREIGN KEY (deal_id) REFERENCES public.deal(deal_id) ON DELETE CASCADE;


--
-- TOC entry 5119 (class 2606 OID 16524)
-- Name: deal_item deal_item_menu_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.deal_item
    ADD CONSTRAINT deal_item_menu_item_id_fkey FOREIGN KEY (menu_item_id) REFERENCES public.menu_item(item_id);


--
-- TOC entry 5145 (class 2606 OID 17238)
-- Name: feedback fk_feedback_order; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT fk_feedback_order FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE SET NULL;


--
-- TOC entry 5146 (class 2606 OID 17233)
-- Name: feedback fk_feedback_user; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE CASCADE;


--
-- TOC entry 5138 (class 2606 OID 17152)
-- Name: kitchen_task_history kitchen_task_history_new_cheff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kitchen_task_history
    ADD CONSTRAINT kitchen_task_history_new_cheff_id_fkey FOREIGN KEY (new_cheff_id) REFERENCES public.chef(cheff_id) ON DELETE SET NULL;


--
-- TOC entry 5139 (class 2606 OID 17147)
-- Name: kitchen_task_history kitchen_task_history_old_cheff_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kitchen_task_history
    ADD CONSTRAINT kitchen_task_history_old_cheff_id_fkey FOREIGN KEY (old_cheff_id) REFERENCES public.chef(cheff_id) ON DELETE SET NULL;


--
-- TOC entry 5140 (class 2606 OID 17142)
-- Name: kitchen_task_history kitchen_task_history_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kitchen_task_history
    ADD CONSTRAINT kitchen_task_history_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE CASCADE;


--
-- TOC entry 5141 (class 2606 OID 17137)
-- Name: kitchen_task_history kitchen_task_history_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kitchen_task_history
    ADD CONSTRAINT kitchen_task_history_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.kitchen_tasks(task_id) ON DELETE CASCADE;


--
-- TOC entry 5120 (class 2606 OID 16541)
-- Name: menu_item_chefs menu_item_chefs_chef_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.menu_item_chefs
    ADD CONSTRAINT menu_item_chefs_chef_id_fkey FOREIGN KEY (chef_id) REFERENCES public.chef(cheff_id);


--
-- TOC entry 5121 (class 2606 OID 16536)
-- Name: menu_item_chefs menu_item_chefs_menu_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.menu_item_chefs
    ADD CONSTRAINT menu_item_chefs_menu_item_id_fkey FOREIGN KEY (menu_item_id) REFERENCES public.menu_item(item_id);


--
-- TOC entry 5137 (class 2606 OID 17032)
-- Name: order_events order_events_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_events
    ADD CONSTRAINT order_events_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE CASCADE;


--
-- TOC entry 5126 (class 2606 OID 16785)
-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE CASCADE;


--
-- TOC entry 5136 (class 2606 OID 17010)
-- Name: order_status_history order_status_history_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT order_status_history_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE CASCADE;


--
-- TOC entry 5123 (class 2606 OID 16810)
-- Name: orders orders_cart_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_cart_id_fkey FOREIGN KEY (cart_id) REFERENCES public.cart(cart_id);


--
-- TOC entry 5128 (class 2606 OID 16906)
-- Name: payments payments_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_card_id_fkey FOREIGN KEY (card_id) REFERENCES public.saved_cards(card_id) ON DELETE RESTRICT;


--
-- TOC entry 5129 (class 2606 OID 16901)
-- Name: payments payments_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE SET NULL;


--
-- TOC entry 5130 (class 2606 OID 16896)
-- Name: payments payments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE CASCADE;


--
-- TOC entry 5127 (class 2606 OID 16891)
-- Name: saved_cards saved_cards_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.saved_cards
    ADD CONSTRAINT saved_cards_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.app_users(user_id) ON DELETE CASCADE;


-- Completed on 2026-03-17 10:33:48

--
-- PostgreSQL database dump complete
--


-- ============================================================
-- Custom Deal Tables — added for custom_deal cart integration
-- ============================================================

CREATE TABLE IF NOT EXISTS public.custom_deals (
    custom_deal_id  SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.app_users(user_id) ON DELETE CASCADE,
    group_size      INTEGER NOT NULL DEFAULT 1,
    total_price     NUMERIC(10,2) NOT NULL,
    discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.custom_deals OWNER TO postgres;


CREATE TABLE IF NOT EXISTS public.custom_deal_items (
    id              SERIAL PRIMARY KEY,
    custom_deal_id  INTEGER NOT NULL REFERENCES public.custom_deals(custom_deal_id) ON DELETE CASCADE,
    item_id         INTEGER NOT NULL REFERENCES public.menu_item(item_id),
    item_name       TEXT NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      NUMERIC(10,2) NOT NULL
);

ALTER TABLE public.custom_deal_items OWNER TO postgres;


-- Allow item_type = 'custom_deal' in cart_items
ALTER TABLE public.cart_items DROP CONSTRAINT IF EXISTS cart_items_item_type_chk;
ALTER TABLE public.cart_items ADD CONSTRAINT cart_items_item_type_chk
    CHECK (item_type = ANY (ARRAY['menu_item'::text, 'deal'::text, 'custom_deal'::text]));

-- Allow item_type = 'custom_deal' in order_items
ALTER TABLE public.order_items DROP CONSTRAINT IF EXISTS order_items_item_type_chk;
ALTER TABLE public.order_items ADD CONSTRAINT order_items_item_type_chk
    CHECK ((item_type)::text = ANY (
        (ARRAY['menu_item'::character varying, 'deal'::character varying, 'custom_deal'::character varying])::text[]
    ));

--- feedback for personal and custom deals ---

ALTER TABLE public.feedback
    ADD COLUMN IF NOT EXISTS item_id INTEGER REFERENCES public.menu_item(item_id) NULL;

ALTER TABLE public.feedback
    ADD COLUMN IF NOT EXISTS deal_id INTEGER REFERENCES public.deal(deal_id) NULL;

ALTER TABLE public.feedback
    DROP CONSTRAINT IF EXISTS feedback_type_chk;

ALTER TABLE public.feedback
    ADD CONSTRAINT feedback_type_chk
    CHECK ((feedback_type)::text = ANY (
        (ARRAY['GENERAL','ORDER','DELIVERY','APP','FOOD','DEAL','CUSTOM_DEAL'])::text[]
    ));

CREATE UNIQUE INDEX IF NOT EXISTS feedback_user_order_unique
    ON public.feedback (user_id, order_id)
    WHERE item_id IS NULL AND order_id IS NOT NULL;



----- For testing ---

SELECT * FROM public.custom_deals ORDER BY created_at DESC LIMIT 3;
SELECT * FROM public.custom_deal_items WHERE custom_deal_id = 5;
SELECT * FROM public.cart_items WHERE item_type = 'custom_deal';

SELECT kt.task_id, kt.order_id, kt.menu_item_id, kt.item_name, kt.qty
FROM kitchen_tasks kt
ORDER BY kt.created_at DESC LIMIT 10;

SELECT order_id, item_id, item_type, quantity
FROM order_items
ORDER BY order_id DESC LIMIT 10;

SELECT * FROM custom_deals ORDER BY created_at DESC LIMIT 3;
SELECT * FROM custom_deal_items ORDER BY id DESC LIMIT 10;

SELECT order_id, item_id, item_type, quantity
FROM order_items
ORDER BY order_id DESC LIMIT 10;

SELECT * FROM custom_deals ORDER BY created_at DESC LIMIT 3;

SELECT * FROM feedback WHERE order_id = 18;

-- ============================================================
-- CUSTOM DEAL FEEDBACK MIGRATION
-- ============================================================

-- Add custom_deal_id column to feedback (nullable FK to custom_deals)
ALTER TABLE public.feedback
    ADD COLUMN IF NOT EXISTS custom_deal_id INTEGER
    REFERENCES public.custom_deals(custom_deal_id) NULL;

-- Add soft_rating column to custom_deal_items for personalization inference
ALTER TABLE public.custom_deal_items
    ADD COLUMN IF NOT EXISTS soft_rating INTEGER NULL;

-- ============================================================
-- FAVOURITES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS public.favourites (
    favourite_id   SERIAL PRIMARY KEY,
    user_id        UUID NOT NULL REFERENCES auth.app_users(user_id) ON DELETE CASCADE,
    item_id        INTEGER REFERENCES public.menu_item(item_id) ON DELETE CASCADE NULL,
    deal_id        INTEGER REFERENCES public.deal(deal_id) ON DELETE CASCADE NULL,
    custom_deal_id INTEGER REFERENCES public.custom_deals(custom_deal_id) ON DELETE CASCADE NULL,
    created_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fav_one_type_only CHECK (
        (item_id IS NOT NULL)::int +
        (deal_id IS NOT NULL)::int +
        (custom_deal_id IS NOT NULL)::int = 1
    ),
    CONSTRAINT fav_unique_user_item UNIQUE (user_id, item_id),
    CONSTRAINT fav_unique_user_deal UNIQUE (user_id, deal_id),
    CONSTRAINT fav_unique_user_custom_deal UNIQUE (user_id, custom_deal_id)
);

-- ============================================================
-- USER PROFILES TABLE  (Phase 2 - Personalization)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.user_profiles (
    profile_id                SERIAL PRIMARY KEY,
    user_id                   UUID NOT NULL UNIQUE
                              REFERENCES auth.app_users(user_id) ON DELETE CASCADE,
    preferred_cuisines        JSONB DEFAULT '[]',
    top_items                 JSONB DEFAULT '[]',
    top_deals                 JSONB DEFAULT '[]',
    disliked_items            JSONB DEFAULT '[]',
    preference_vector         JSONB DEFAULT '{}',
    cached_recommendations    JSONB DEFAULT NULL,
    cached_recommendations_ts TIMESTAMP DEFAULT NULL,
    last_updated              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id
    ON public.user_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_updated
    ON public.user_profiles(last_updated);
CREATE INDEX IF NOT EXISTS idx_user_profiles_cache_ts
    ON public.user_profiles(cached_recommendations_ts);


-----------------------------------------------------
------------------ admin profile --------------------
-----------------------------------------------------

INSERT INTO auth.app_users (full_name, email, password_hash, is_active)
VALUES (
    'Admin',
    'admin@gmail.com',
    '$argon2id$v=19$m=65536,t=3,p=4$7h0jRIjxHgPgHEPIOWcsRQ$IQmy+119dEKCCGNX7WZFoKgDjvkE7y9ir3cQ6xTbtxA',
    TRUE
)
ON CONFLICT (email) DO UPDATE


-- ============================================
-- DINE-IN FEATURE TABLES 
-- Added: March 31, 2026
-- ============================================

CREATE TABLE IF NOT EXISTS public.restaurant_tables (
    table_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_number VARCHAR(10) NOT NULL,
    table_pin   VARCHAR(6) NOT NULL,
    qr_token    VARCHAR(64) UNIQUE,
    status      VARCHAR(30) DEFAULT 'available',
    created_at  TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tables_status ON public.restaurant_tables(status);


CREATE TABLE IF NOT EXISTS public.dine_in_sessions (
    session_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id       UUID NOT NULL REFERENCES public.restaurant_tables(table_id) ON DELETE CASCADE,
    started_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at       TIMESTAMP WITHOUT TIME ZONE,
    status         VARCHAR(30) DEFAULT 'active',
    payment_method VARCHAR(20),
    total_amount   NUMERIC(10,2) DEFAULT 0,
    round_count    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_table  ON public.dine_in_sessions(table_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON public.dine_in_sessions(status);



ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS order_type      VARCHAR(20) DEFAULT 'delivery',
    ADD COLUMN IF NOT EXISTS table_id        UUID REFERENCES public.restaurant_tables(table_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS session_id      UUID REFERENCES public.dine_in_sessions(session_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS round_number    INTEGER,
    ADD COLUMN IF NOT EXISTS payment_status  VARCHAR(20) DEFAULT NULL;


-- 1. waiter_calls table
CREATE TABLE IF NOT EXISTS waiter_calls (
    call_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id UUID REFERENCES restaurant_tables(table_id),
    called_at TIMESTAMP DEFAULT NOW(),
    resolved BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_waiter_calls_resolved 
    ON waiter_calls(resolved);

CREATE INDEX IF NOT EXISTS idx_waiter_calls_table
    ON waiter_calls(table_id);